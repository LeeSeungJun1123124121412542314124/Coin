"""
백테스트 엔진 — 현재 시스템 vs 통합 시스템 비교.

평가 기준:
  - 시그널: technical signal = HIGH or MEDIUM (volatility elevated)
  - 오탐(FP): 시그널 후 4h 내 가격 변동 < 1.5% (아무 일도 없었음)
  - 적중(TP): 시그널 후 4h 내 가격 변동 >= 1.5%
  - 시그널 캐치율: 실제 1.5% 이상 변동 이벤트 중 사전 감지한 비율

통합 시스템 추가 필터:
  1. OI 3일 변화율 필터 — OI 급등(3d > 15%) 시 HIGH 시그널 신뢰도 가중
  2. FR 극단값 필터 — |FR| > 0.08% 시 쏠림 과열 → 시그널 강화
  3. OI+FR 복합 — OI 급등 + FR 극단 동시 → 청산 캐스케이드 선행 경보
"""

from __future__ import annotations

import sys
from pathlib import Path

# 봇 패키지 경로 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "crypto-volatility-bot"))

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from app.analyzers.technical_analyzer import TechnicalAnalyzer

DATA_DIR = Path(__file__).parent / "data"
RESULT_DIR = Path(__file__).parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

# ─── 설정 ───────────────────────────────────────────────────────────────────
WINDOW_1H = 200       # 기술적 분석 롤링 윈도우
WINDOW_4H = 50        # 4h 멀티타임프레임 윈도우
STEP = 1              # 1시간마다 평가
MOVE_THRESHOLD = 1.5  # 적중 판정 기준 (%)
EVAL_HORIZON_H = 4    # 시그널 후 평가 시간 (시간)

# OI/FR 필터 임계값
OI_3D_SURGE = 12.0    # OI 3일 변화 12% 이상 = 과열
FR_EXTREME = 0.07     # |FR| 0.07% 이상 = 극단 쏠림
FR_EXTREME_SHORT = -0.02  # FR 음수 = 숏 쏠림


# ─── 데이터 로드 ─────────────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df_1h = pd.read_csv(DATA_DIR / "btc_1h.csv", parse_dates=["datetime"])
    df_4h = pd.read_csv(DATA_DIR / "btc_4h.csv", parse_dates=["datetime"])
    df_oi = pd.read_csv(DATA_DIR / "btc_oi_daily.csv", parse_dates=["datetime"])
    df_fr = pd.read_csv(DATA_DIR / "btc_fr_8h.csv", parse_dates=["datetime"])

    # UTC 통일
    for df in [df_1h, df_4h, df_oi, df_fr]:
        if df["datetime"].dt.tz is None:
            df["datetime"] = df["datetime"].dt.tz_localize("UTC")

    return df_1h, df_4h, df_oi, df_fr


# ─── OI/FR 지표 계산 ────────────────────────────────────────────────────────

def build_oi_fr_features(df_oi: pd.DataFrame, df_fr: pd.DataFrame) -> pd.DataFrame:
    """시간별 OI/FR 특징 계산."""
    # OI: 일별 데이터를 날짜 기준으로 인덱스화
    oi = df_oi.set_index("datetime")["open_interest"]
    oi_3d_chg = oi.pct_change(3) * 100    # 3일 변화율 (%)
    oi_7d_chg = oi.pct_change(7) * 100
    oi_series = pd.DataFrame({
        "oi": oi,
        "oi_3d_chg": oi_3d_chg,
        "oi_7d_chg": oi_7d_chg,
    })

    # FR: 8h 데이터를 날짜 기준으로 합산 (3일 누적)
    fr = df_fr.set_index("datetime")["funding_rate"]
    fr_cum_3d = fr.rolling(9).sum()  # 9 * 8h = 72h = 3일
    fr_series = pd.DataFrame({
        "fr": fr,
        "fr_cum_3d": fr_cum_3d,
    })

    return oi_series, fr_series


def get_oi_fr_at(ts: pd.Timestamp, oi_series: pd.DataFrame, fr_series: pd.DataFrame) -> dict:
    """특정 시간의 OI/FR 특징 조회."""
    # OI: ts 이전 마지막 일별 값
    ts_date = ts.normalize()
    oi_rows = oi_series[oi_series.index.normalize() <= ts_date.normalize()]
    if oi_rows.empty:
        oi_3d = 0.0
        oi_7d = 0.0
    else:
        last = oi_rows.iloc[-1]
        oi_3d = float(last["oi_3d_chg"]) if not np.isnan(last["oi_3d_chg"]) else 0.0
        oi_7d = float(last["oi_7d_chg"]) if not np.isnan(last["oi_7d_chg"]) else 0.0

    # FR: ts 이전 마지막 8h 값
    fr_rows = fr_series[fr_series.index <= ts]
    if fr_rows.empty:
        fr_val = 0.0
        fr_cum = 0.0
    else:
        last_fr = fr_rows.iloc[-1]
        fr_val = float(last_fr["fr"])
        fr_cum = float(last_fr["fr_cum_3d"]) if not np.isnan(last_fr["fr_cum_3d"]) else fr_val

    return {
        "oi_3d_chg": oi_3d,
        "oi_7d_chg": oi_7d,
        "fr": fr_val,
        "fr_cum_3d": fr_cum,
        "oi_surge": abs(oi_3d) > OI_3D_SURGE,
        "fr_extreme_long": fr_val > FR_EXTREME,
        "fr_extreme_short": fr_val < FR_EXTREME_SHORT,
        "liquidation_risk": abs(oi_3d) > OI_3D_SURGE and abs(fr_val) > FR_EXTREME,
    }


# ─── 시그널 평가 ─────────────────────────────────────────────────────────────

def evaluate_signal(signal: str, df_future: pd.DataFrame) -> dict:
    """시그널 발생 후 EVAL_HORIZON_H 시간 내 실제 움직임 평가."""
    if len(df_future) < EVAL_HORIZON_H:
        return {"valid": False}

    entry_price = float(df_future.iloc[0]["close"])
    future_slice = df_future.iloc[1: EVAL_HORIZON_H + 1]

    max_high = float(future_slice["high"].max())
    min_low = float(future_slice["low"].min())

    up_move = (max_high - entry_price) / entry_price * 100
    down_move = (entry_price - min_low) / entry_price * 100
    max_move = max(up_move, down_move)

    return {
        "valid": True,
        "entry_price": entry_price,
        "max_move_pct": round(max_move, 3),
        "up_move_pct": round(up_move, 3),
        "down_move_pct": round(down_move, 3),
        "is_tp": max_move >= MOVE_THRESHOLD,  # True Positive
        "is_fp": max_move < MOVE_THRESHOLD,   # False Positive
    }


# ─── 메인 백테스트 루프 ──────────────────────────────────────────────────────

def run_backtest(df_1h: pd.DataFrame, df_4h: pd.DataFrame,
                 oi_series: pd.DataFrame, fr_series: pd.DataFrame) -> pd.DataFrame:
    """롤링 윈도우 백테스트."""
    analyzer = TechnicalAnalyzer()
    records: list[dict] = []

    total = len(df_1h) - WINDOW_1H - EVAL_HORIZON_H
    print(f"  총 평가 포인트: {total:,}건 (step={STEP})")

    for i in range(0, total, STEP):
        window_end = i + WINDOW_1H
        df_window = df_1h.iloc[i: window_end].copy()

        # OHLCV 컬럼 정렬
        df_window = df_window[["open", "high", "low", "close", "volume"]].reset_index(drop=True)

        # 4h 윈도우 (현재 시간 이전 50봉)
        current_ts = df_1h.iloc[window_end - 1]["datetime"]
        df_4h_window = df_4h[df_4h["datetime"] <= current_ts].tail(WINDOW_4H).copy()
        df_4h_window = df_4h_window[["open", "high", "low", "close", "volume"]].reset_index(drop=True)

        # 기술적 분석 실행
        try:
            result = analyzer.analyze(df_window, df_4h=df_4h_window if len(df_4h_window) >= 20 else None)
        except Exception:
            continue

        signal = result.signal
        score = result.score
        base_score = result.details.get("base_score", score)
        boost = result.details.get("signal_boost", {}).get("total_boost", 0.0)
        active_boosters = result.details.get("signal_boost", {}).get("active_boosters", {})

        # OI/FR 특징
        oifr = get_oi_fr_at(current_ts, oi_series, fr_series)

        # 미래 가격 평가
        df_future = df_1h.iloc[window_end - 1: window_end + EVAL_HORIZON_H]
        eval_result = evaluate_signal(signal, df_future)
        if not eval_result["valid"]:
            continue

        # 통합 시스템: OI/FR 필터 적용
        # - OI 급등 + FR 극단 = 청산 위험 → HIGH 보정
        # - OI/FR 정상 + 기술적만 HIGH = 오탐 가능성 높음
        enhanced_signal = signal
        if signal == "HIGH" and not oifr["oi_surge"] and not oifr["fr_extreme_long"] and not oifr["fr_extreme_short"]:
            # 파생상품 확인 없는 HIGH → MEDIUM으로 하향
            enhanced_signal = "MEDIUM_DOWNGRADED"
        elif signal in ("LOW", "MEDIUM") and oifr["liquidation_risk"]:
            # 기술적으론 낮지만 OI+FR 청산 위험 → 경보 추가
            enhanced_signal = "LIQUIDATION_RISK"

        records.append({
            "timestamp": current_ts,
            "close": float(df_1h.iloc[window_end - 1]["close"]),
            # 현재 시스템
            "signal": signal,
            "score": round(score, 2),
            "base_score": round(base_score, 2),
            "boost": round(boost, 2),
            "active_boosters": "|".join(active_boosters.keys()) if active_boosters else "",
            # OI/FR 특징
            "oi_3d_chg": round(oifr["oi_3d_chg"], 2),
            "oi_7d_chg": round(oifr["oi_7d_chg"], 2),
            "fr": round(oifr["fr"], 6),
            "fr_cum_3d": round(oifr["fr_cum_3d"], 6),
            "oi_surge": oifr["oi_surge"],
            "fr_extreme_long": oifr["fr_extreme_long"],
            "fr_extreme_short": oifr["fr_extreme_short"],
            "liquidation_risk": oifr["liquidation_risk"],
            # 통합 시스템
            "enhanced_signal": enhanced_signal,
            # 평가 결과
            "max_move_pct": eval_result["max_move_pct"],
            "up_move_pct": eval_result["up_move_pct"],
            "down_move_pct": eval_result["down_move_pct"],
            "is_tp": eval_result["is_tp"],
            "is_fp": eval_result["is_fp"],
        })

        if len(records) % 1000 == 0:
            print(f"  진행: {len(records):,}/{total:,}건 처리...")

    return pd.DataFrame(records)


# ─── 결과 분석 ───────────────────────────────────────────────────────────────

def analyze_results(df: pd.DataFrame) -> dict:
    """백테스트 결과 지표 계산."""
    results = {}

    # ── 현재 시스템 ─────────────────────────────────────────────
    for sig in ["HIGH", "MEDIUM", "LOW"]:
        subset = df[df["signal"] == sig]
        if len(subset) == 0:
            continue
        tp = subset["is_tp"].sum()
        fp = subset["is_fp"].sum()
        total = len(subset)
        results[f"current_{sig.lower()}_count"] = total
        results[f"current_{sig.lower()}_tp"] = int(tp)
        results[f"current_{sig.lower()}_fp"] = int(fp)
        results[f"current_{sig.lower()}_precision"] = round(tp / total * 100, 1) if total > 0 else 0
        results[f"current_{sig.lower()}_fp_rate"] = round(fp / total * 100, 1) if total > 0 else 0

    # 전체 실제 변동 이벤트 수 (1.5% 이상)
    total_events = df["is_tp"].sum()
    results["total_actual_events"] = int(total_events)

    # 현재 시스템 recall (HIGH+MEDIUM 시그널로 이벤트 캐치율)
    high_med = df[df["signal"].isin(["HIGH", "MEDIUM"])]
    caught = high_med["is_tp"].sum()
    results["current_recall"] = round(caught / total_events * 100, 1) if total_events > 0 else 0

    # ── 통합 시스템 ──────────────────────────────────────────────
    # HIGH 유지 (파생상품 확인된 HIGH)
    enh_high = df[df["enhanced_signal"] == "HIGH"]
    if len(enh_high) > 0:
        enh_tp = enh_high["is_tp"].sum()
        results["enhanced_high_count"] = len(enh_high)
        results["enhanced_high_precision"] = round(enh_tp / len(enh_high) * 100, 1)
        results["enhanced_high_fp_rate"] = round((len(enh_high) - enh_tp) / len(enh_high) * 100, 1)

    # MEDIUM_DOWNGRADED (기술적 HIGH였지만 파생상품 미확인)
    downgraded = df[df["enhanced_signal"] == "MEDIUM_DOWNGRADED"]
    if len(downgraded) > 0:
        dg_tp = downgraded["is_tp"].sum()
        results["downgraded_count"] = len(downgraded)
        results["downgraded_precision"] = round(dg_tp / len(downgraded) * 100, 1)

    # LIQUIDATION_RISK (신규 시그널)
    liq_risk = df[df["enhanced_signal"] == "LIQUIDATION_RISK"]
    if len(liq_risk) > 0:
        lr_tp = liq_risk["is_tp"].sum()
        results["liq_risk_count"] = len(liq_risk)
        results["liq_risk_precision"] = round(lr_tp / len(liq_risk) * 100, 1)

    # 통합 시스템 recall
    enh_signals = df[df["enhanced_signal"].isin(["HIGH", "MEDIUM", "LIQUIDATION_RISK"])]
    enh_caught = enh_signals["is_tp"].sum()
    results["enhanced_recall"] = round(enh_caught / total_events * 100, 1) if total_events > 0 else 0

    # ── 파생상품 단독 지표 성능 ──────────────────────────────────
    oi_surge_events = df[df["oi_surge"]]
    if len(oi_surge_events) > 0:
        results["oi_surge_count"] = len(oi_surge_events)
        results["oi_surge_precision"] = round(oi_surge_events["is_tp"].mean() * 100, 1)

    liq_events = df[df["liquidation_risk"]]
    if len(liq_events) > 0:
        results["liquidation_risk_precision"] = round(liq_events["is_tp"].mean() * 100, 1)
        results["liquidation_risk_count"] = len(liq_events)

    return results


# ─── 진입점 ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("백테스트 실행")
    print("=" * 60)

    print("\n[1/3] 데이터 로드...")
    df_1h, df_4h, df_oi, df_fr = load_data()
    oi_series, fr_series = build_oi_fr_features(df_oi, df_fr)
    print(f"  1h: {len(df_1h)}건 | 4h: {len(df_4h)}건 | OI: {len(df_oi)}건 | FR: {len(df_fr)}건")

    print("\n[2/3] 롤링 백테스트 실행...")
    df_results = run_backtest(df_1h, df_4h, oi_series, fr_series)
    out_path = RESULT_DIR / "backtest_raw.csv"
    df_results.to_csv(out_path, index=False)
    print(f"  원시 결과 저장: {out_path} ({len(df_results)}건)")

    print("\n[3/3] 성능 지표 분석...")
    metrics = analyze_results(df_results)

    print("\n" + "=" * 60)
    print("현재 시스템 성능")
    print("=" * 60)
    print(f"  총 실제 변동 이벤트 (>{MOVE_THRESHOLD}%): {metrics.get('total_actual_events', 0):,}건")
    print()
    for sig in ["high", "medium", "low"]:
        cnt = metrics.get(f"current_{sig}_count", 0)
        prec = metrics.get(f"current_{sig}_precision", 0)
        fp = metrics.get(f"current_{sig}_fp_rate", 0)
        tp = metrics.get(f"current_{sig}_tp", 0)
        print(f"  {sig.upper():6s}: {cnt:5,}건 | 정밀도 {prec:5.1f}% | 오탐률 {fp:5.1f}% | TP {tp:,}건")
    print(f"\n  시그널 캐치율 (Recall): {metrics.get('current_recall', 0):.1f}%")

    print("\n" + "=" * 60)
    print("통합 시스템 성능 (OI/FR 필터 적용)")
    print("=" * 60)
    enh_cnt = metrics.get("enhanced_high_count", 0)
    enh_prec = metrics.get("enhanced_high_precision", 0)
    enh_fp = metrics.get("enhanced_high_fp_rate", 0)
    dg_cnt = metrics.get("downgraded_count", 0)
    dg_prec = metrics.get("downgraded_precision", 0)
    lr_cnt = metrics.get("liq_risk_count", 0)
    lr_prec = metrics.get("liq_risk_precision", 0)
    print(f"  HIGH (파생상품 확인): {enh_cnt:,}건 | 정밀도 {enh_prec:.1f}% | 오탐률 {enh_fp:.1f}%")
    print(f"  HIGH→하향 (파생상품 미확인): {dg_cnt:,}건 | 정밀도 {dg_prec:.1f}%")
    print(f"  청산 위험 (신규 시그널): {lr_cnt:,}건 | 정밀도 {lr_prec:.1f}%")
    print(f"\n  시그널 캐치율 (Recall): {metrics.get('enhanced_recall', 0):.1f}%")

    print("\n" + "=" * 60)
    print("파생상품 단독 지표 성능")
    print("=" * 60)
    print(f"  OI 3일 급등: {metrics.get('oi_surge_count', 0):,}건 | 정밀도 {metrics.get('oi_surge_precision', 0):.1f}%")
    print(f"  OI+FR 청산위험: {metrics.get('liquidation_risk_count', 0):,}건 | 정밀도 {metrics.get('liquidation_risk_precision', 0):.1f}%")

    # 메트릭 저장
    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(RESULT_DIR / "metrics.csv", index=False)

    # 월별 분석
    df_results["month"] = df_results["timestamp"].dt.to_period("M")
    monthly = df_results.groupby("month").agg(
        signals=("signal", lambda x: (x.isin(["HIGH", "MEDIUM"])).sum()),
        tp=("is_tp", "sum"),
        total=("is_tp", "count"),
    )
    monthly["precision"] = (monthly["tp"] / monthly["signals"].clip(lower=1) * 100).round(1)
    monthly.to_csv(RESULT_DIR / "monthly_breakdown.csv")
    print(f"\n월별 분석 저장: {RESULT_DIR / 'monthly_breakdown.csv'}")

    print("\n완료!")
    return df_results, metrics


if __name__ == "__main__":
    df_results, metrics = main()
