"""CVD(Cumulative Volume Delta) 계산 + 11팩터 스크리너.

CVD = 누적 (매수 체결량 - 매도 체결량)
  - 가격 상승 + CVD 하락 → 하락 다이버전스 (약세)
  - 가격 하락 + CVD 상승 → 상승 다이버전스 (강세)

11팩터 스크리너:
  1. CVD 방향 vs 가격 방향 (다이버전스)
  2. CVD 기울기 (3봉 선형 회귀)
  3. RSI (봇 지표 재활용)
  4. BB %B (봇 지표 재활용)
  5. BB 밴드폭 (스퀴즈 감지)
  6. OI 변화
  7. FR (펀딩비)
  8. 거래량 상대 강도
  9. 고가/저가 대비 종가 위치
  10. ATR 기반 변동성
  11. 추세 강도 (EMA 정렬)

총점 0~100 → 등급: S(80+), A(65+), B(50+), C(35+), D(미만)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dashboard.backend.cache import cached

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 스크리너 대상 종목
SCREENER_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT",
    "BNB/USDT", "AVAX/USDT", "LINK/USDT",
    "INJ/USDT", "HYPE/USDT", "ONDO/USDT",
    "SUI/USDT", "TIA/USDT", "JUP/USDT",
]

GRADE_THRESHOLDS = [
    (80, "S"), (65, "A"), (50, "B"), (35, "C"), (0, "D"),
]


def grade(score: float) -> str:
    for threshold, label in GRADE_THRESHOLDS:
        if score >= threshold:
            return label
    return "D"


def calc_cvd(df: pd.DataFrame) -> pd.Series:
    """캔들 데이터로 CVD 근사 계산.

    완벽한 CVD는 틱 데이터 필요 → 캔들 기반 근사:
      각 캔들 CVD = (종가 - 시가) / (고가 - 저가 + 1e-8) * 거래량
    """
    if "volume" not in df.columns:
        return pd.Series(dtype=float)

    price_range = df["high"] - df["low"] + 1e-8
    delta = (df["close"] - df["open"]) / price_range * df["volume"]
    cvd = delta.cumsum()
    return cvd


def calc_cvd_slope(cvd: pd.Series, window: int = 3) -> float:
    """CVD 최근 N봉 선형 회귀 기울기 (정규화)."""
    if len(cvd) < window:
        return 0.0
    recent = cvd.iloc[-window:].values
    x = np.arange(window)
    if recent.std() == 0:
        return 0.0
    # 정규화 기울기 (-1 ~ 1)
    slope = np.polyfit(x, recent, 1)[0]
    norm = slope / (abs(recent).mean() + 1e-8)
    return float(np.clip(norm, -1, 1))


def calc_divergence_score(df: pd.DataFrame, cvd: pd.Series, window: int = 10) -> float:
    """CVD vs 가격 다이버전스 점수 (0~100).

    다이버전스 없음 + CVD 상승 = 강세 (높은 점수)
    하락 다이버전스 = 약세 (낮은 점수)
    """
    if len(df) < window or len(cvd) < window:
        return 50.0

    price_change = (df["close"].iloc[-1] - df["close"].iloc[-window]) / (df["close"].iloc[-window] + 1e-8)
    cvd_change = (cvd.iloc[-1] - cvd.iloc[-window]) / (abs(cvd.iloc[-window]) + 1e-8)

    # 같은 방향 = 확인, 반대 방향 = 다이버전스
    if price_change > 0 and cvd_change > 0:
        # 상승 확인 — 강세
        return min(80.0, 50.0 + abs(cvd_change) * 30)
    elif price_change < 0 and cvd_change < 0:
        # 하락 확인 — 약세
        return max(20.0, 50.0 - abs(cvd_change) * 30)
    elif price_change > 0 and cvd_change < 0:
        # 하락 다이버전스 (위험)
        return max(10.0, 30.0 - abs(cvd_change) * 20)
    elif price_change < 0 and cvd_change > 0:
        # 상승 다이버전스 (기회)
        return min(90.0, 70.0 + abs(cvd_change) * 20)
    return 50.0


def calc_volume_strength(df: pd.DataFrame, window: int = 20) -> float:
    """현재 거래량 / 최근 N봉 평균 거래량 → 0~100."""
    if "volume" not in df.columns or len(df) < window:
        return 50.0
    avg_vol = df["volume"].iloc[-window:].mean()
    if avg_vol == 0:
        return 50.0
    ratio = df["volume"].iloc[-1] / avg_vol
    return float(min(100.0, ratio * 50))  # 평균의 2배 = 100점


def calc_close_position(df: pd.DataFrame) -> float:
    """고가/저가 대비 종가 위치 (0=저점, 100=고점)."""
    high = df["high"].iloc[-1]
    low = df["low"].iloc[-1]
    close = df["close"].iloc[-1]
    if high == low:
        return 50.0
    return float((close - low) / (high - low) * 100)


def calc_atr_score(df: pd.DataFrame, window: int = 14) -> float:
    """ATR 기반 변동성 점수 (변동성 낮을수록 진입 유리 → 높은 점수)."""
    if len(df) < window + 1:
        return 50.0
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift(1))
    low_close = abs(df["low"] - df["close"].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window).mean().iloc[-1]
    close = df["close"].iloc[-1]
    if close == 0:
        return 50.0
    atr_pct = atr / close
    # ATR 2% 이하 = 낮은 변동성 = 진입 적합
    score = max(0.0, min(100.0, (0.04 - atr_pct) / 0.04 * 100))
    return score


def calc_ema_trend(df: pd.DataFrame) -> float:
    """EMA 정렬 추세 강도 (EMA9 > EMA21 > EMA55 = 100, 반전 = 0)."""
    close = df["close"]
    if len(close) < 55:
        return 50.0
    ema9  = close.ewm(span=9,  adjust=False).mean().iloc[-1]
    ema21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
    ema55 = close.ewm(span=55, adjust=False).mean().iloc[-1]

    if ema9 > ema21 > ema55:
        return 85.0  # 상승 정렬
    elif ema9 < ema21 < ema55:
        return 15.0  # 하락 정렬
    elif ema9 > ema21:
        return 60.0  # 단기 상승
    elif ema9 < ema21:
        return 40.0  # 단기 하락
    return 50.0


def score_symbol(
    df: pd.DataFrame,
    oi_change_3d: float | None = None,
    funding_rate: float | None = None,
) -> dict[str, Any]:
    """단일 종목 11팩터 스코어 산출."""
    try:
        from app.analyzers.indicators.rsi import calculate as calc_rsi
        from app.analyzers.indicators.bollinger_bands import calculate as calc_bb

        if df is None or len(df) < 20:
            return {"score": 0, "grade": "D", "factors": {}, "error": "데이터 부족"}

        cvd = calc_cvd(df)
        if cvd.empty:
            return {"score": 0, "grade": "D", "factors": {}, "error": "CVD 계산 실패"}

        # 11개 팩터 계산
        factors: dict[str, float] = {}

        # 1. CVD 다이버전스
        factors["cvd_divergence"] = calc_divergence_score(df, cvd)

        # 2. CVD 기울기 (-1~1 → 0~100)
        slope = calc_cvd_slope(cvd)
        factors["cvd_slope"] = (slope + 1) / 2 * 100

        # 3. RSI
        try:
            rsi_result = calc_rsi(df, period=14)
            rsi_val = rsi_result.get("rsi", 50)
            # RSI 30~70 정상 구간 → 50점 기준, 과매도(30이하) = 강세 신호
            if rsi_val <= 30:
                factors["rsi"] = 80.0
            elif rsi_val >= 70:
                factors["rsi"] = 20.0
            else:
                factors["rsi"] = 50.0 - (rsi_val - 50) * 0.5
        except Exception:
            factors["rsi"] = 50.0

        # 4. BB %B
        try:
            bb_result = calc_bb(df)
            pct_b = bb_result.get("percent_b", 0.5)
            # %B 0.2 이하 = 과매도 강세, 0.8 이상 = 과매수 약세
            if pct_b <= 0.2:
                factors["bb_pct_b"] = 80.0
            elif pct_b >= 0.8:
                factors["bb_pct_b"] = 20.0
            else:
                factors["bb_pct_b"] = (0.8 - pct_b) / 0.6 * 100
        except Exception:
            factors["bb_pct_b"] = 50.0

        # 5. BB 스퀴즈 (밴드폭 좁음 = 폭발 임박)
        try:
            bw = bb_result.get("bandwidth", 0.02)
            # 밴드폭 1% 이하 = 스퀴즈 = 방향성 확인 시 강한 진입 신호
            factors["bb_squeeze"] = max(0.0, min(100.0, (0.04 - bw) / 0.04 * 100))
        except Exception:
            factors["bb_squeeze"] = 50.0

        # 6. OI 변화
        if oi_change_3d is not None:
            oi_pct = oi_change_3d * 100
            if -5 <= oi_pct <= 5:
                factors["oi_change"] = 65.0  # 안정 = 우호
            elif oi_pct > 15:
                factors["oi_change"] = 20.0  # 급등 = 청산 위험
            elif oi_pct < -10:
                factors["oi_change"] = 40.0  # 감소 = 포지션 정리
            else:
                factors["oi_change"] = 50.0
        else:
            factors["oi_change"] = 50.0

        # 7. 펀딩비
        if funding_rate is not None:
            fr_pct = funding_rate * 100
            if fr_pct < -0.01:
                factors["funding_rate"] = 75.0  # 음수 = 숏 과밀 = 반등 기대
            elif fr_pct > 0.04:
                factors["funding_rate"] = 20.0  # 과열 = 위험
            else:
                factors["funding_rate"] = 55.0
        else:
            factors["funding_rate"] = 50.0

        # 8. 거래량 강도
        factors["volume_strength"] = calc_volume_strength(df)

        # 9. 종가 위치
        factors["close_position"] = calc_close_position(df)

        # 10. ATR 변동성
        factors["atr"] = calc_atr_score(df)

        # 11. EMA 추세
        factors["ema_trend"] = calc_ema_trend(df)

        # 가중 평균
        weights = {
            "cvd_divergence": 2.0,
            "cvd_slope": 1.5,
            "rsi": 1.5,
            "bb_pct_b": 1.0,
            "bb_squeeze": 0.8,
            "oi_change": 1.2,
            "funding_rate": 1.0,
            "volume_strength": 0.8,
            "close_position": 0.7,
            "atr": 0.5,
            "ema_trend": 1.5,
        }
        total_weight = sum(weights.values())
        weighted_sum = sum(factors[k] * weights[k] for k in factors)
        final_score = round(weighted_sum / total_weight, 1)

        return {
            "score": final_score,
            "grade": grade(final_score),
            "factors": {k: round(v, 1) for k, v in factors.items()},
        }

    except Exception as e:
        logger.error("종목 스코어 계산 실패: %s", e)
        return {"score": 0, "grade": "D", "factors": {}, "error": str(e)}


async def _process_symbol(symbol: str, timeframe: str, collector, loop) -> dict | None:
    """단일 종목 CVD 스코어 계산 (병렬 처리용 헬퍼)."""
    from dashboard.backend.collectors.bybit_derivatives import (
        fetch_open_interest, fetch_funding_rate,
    )
    try:
        binance_symbol = symbol.replace("/", "").replace("USDT", "USDT")

        df, oi, fr = await asyncio.gather(
            loop.run_in_executor(None, collector.fetch_ohlcv, symbol, timeframe, 100),
            fetch_open_interest(binance_symbol),
            fetch_funding_rate(binance_symbol),
            return_exceptions=True,
        )

        if isinstance(df, Exception) or df is None:
            return None

        oi_change = None
        if not isinstance(oi, Exception) and oi:
            oi_change = _get_btc_oi_change_from_db()

        # funding_rate는 dict로 반환됨 → float 추출
        fr_val = None
        if isinstance(fr, dict):
            fr_val = fr.get("funding_rate")
        elif isinstance(fr, (int, float)):
            fr_val = fr

        score_result = score_symbol(df, oi_change, fr_val)
        return {"symbol": symbol, **score_result}

    except Exception as e:
        logger.error("스크리너 %s 실패: %s", symbol, e)
        return None


@cached(120, "cvd_screener")
async def run_screener(timeframe: str = "4h") -> list[dict]:
    """전체 SCREENER_SYMBOLS에 대해 스코어 계산 후 정렬 (병렬 처리)."""
    from app.data.data_collector import DataCollector

    loop = asyncio.get_running_loop()

    # 종목별 DataCollector 생성 (ccxt exchange는 스레드 안전하지 않음)
    raw = await asyncio.gather(
        *[_process_symbol(s, timeframe, DataCollector(), loop) for s in SCREENER_SYMBOLS],
        return_exceptions=True,
    )

    results = [r for r in raw if r is not None and not isinstance(r, Exception)]
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _get_btc_oi_change_from_db() -> float | None:
    """spf_records에서 BTC OI 3일 변화율 조회 (시장 대리지표 — BTC 전용)."""
    try:
        from dashboard.backend.db.connection import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT oi_change_3d FROM spf_records ORDER BY date DESC LIMIT 1"
            ).fetchone()
        return row["oi_change_3d"] if row else None
    except Exception:
        return None


def get_cvd_chart(df: pd.DataFrame) -> list[dict]:
    """CVD 차트 데이터 생성 (프론트 표시용)."""
    if df is None or df.empty:
        return []

    cvd = calc_cvd(df)
    if cvd.empty:
        return []

    result = []
    for i, (idx, cvd_val) in enumerate(cvd.items()):
        date_str = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        result.append({
            "date": date_str,
            "cvd": round(float(cvd_val), 2),
            "close": round(float(df["close"].iloc[i]), 2) if i < len(df) else None,
        })
    return result
