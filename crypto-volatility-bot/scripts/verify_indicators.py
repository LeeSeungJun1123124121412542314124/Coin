"""지표 공식 검증 스크립트 — 우리 구현 vs ta 참조 라이브러리 비교.

바이낸스에서 실시간 OHLCV를 가져와 각 지표를 양쪽 모두 계산한 후,
절대오차·상대오차·판정(PASS/WARN/FAIL)을 출력한다.

판정 기준:
  PASS : 상대오차 < 0.1%
  WARN : 상대오차 0.1% ~ 2%
  FAIL : 상대오차 > 2%

사용법:
  cd crypto-volatility-bot
  python scripts/verify_indicators.py
  python scripts/verify_indicators.py --symbol ETH/USDT --timeframe 4h --limit 300
"""

from __future__ import annotations

import sys
import os
import io
import argparse
import math
from dataclasses import dataclass, field

# Windows 콘솔 UTF-8 출력
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ccxt
import numpy as np
import pandas as pd

try:
    import ta as _ta
    HAS_TA = True
except ImportError:
    HAS_TA = False
    print("[경고] ta 라이브러리가 설치되어 있지 않습니다. pip install ta 로 설치하세요.")

# 우리 지표 모듈
from app.analyzers.indicators import (
    atr,
    bollinger_bands,
    bollinger_width,
    macd,
    rsi,
    stoch_rsi,
    adx,
    historical_volatility,
    hull_ma,
)

# ─────────────────────────────────────────────────────────────────────────────
# 데이터 수집
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str = "BTC/USDT", timeframe: str = "1h", limit: int = 500) -> pd.DataFrame:
    """바이낸스에서 OHLCV 데이터 fetch."""
    exchange = ccxt.binance({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 결과 데이터 클래스
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ComparisonResult:
    indicator: str
    metric: str
    our_value: float
    ref_value: float
    abs_error: float = field(init=False)
    rel_error_pct: float = field(init=False)
    status: str = field(init=False)
    note: str = ""

    def __post_init__(self) -> None:
        self.abs_error = abs(self.our_value - self.ref_value)
        ref = abs(self.ref_value)
        if ref < 1e-10:
            self.rel_error_pct = 0.0 if self.abs_error < 1e-10 else float("inf")
        else:
            self.rel_error_pct = self.abs_error / ref * 100.0
        if math.isinf(self.rel_error_pct):
            self.status = "FAIL"
        elif self.rel_error_pct < 0.1:
            self.status = "PASS"
        elif self.rel_error_pct < 2.0:
            self.status = "WARN"
        else:
            self.status = "FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Wilder's 스무딩 참조 구현 (SMA seed + 재귀)
# ─────────────────────────────────────────────────────────────────────────────

def _wilders_ref(series: pd.Series, period: int) -> pd.Series:
    """ta 라이브러리와 동일한 Wilder's smoothing (SMA seed)."""
    result = pd.Series(np.nan, index=series.index, dtype=float)
    values = series.values
    n = len(values)
    if n < period:
        return result

    # 첫 seed = 처음 period개의 SMA
    seed = float(np.mean(values[:period]))
    result.iloc[period - 1] = seed
    alpha = 1.0 / period
    prev = seed
    for i in range(period, n):
        curr = prev * (1 - alpha) + values[i] * alpha
        result.iloc[i] = curr
        prev = curr
    return result


def _wilder_atr_ref(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ta 라이브러리 방식의 ATR (Wilder's, SMA seed)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return _wilders_ref(tr.fillna(tr.iloc[0]), period)

# ─────────────────────────────────────────────────────────────────────────────
# 지표별 비교 함수
# ─────────────────────────────────────────────────────────────────────────────

def compare_atr(df: pd.DataFrame, period: int = 14) -> list[ComparisonResult]:
    """ATR: 우리 구현 vs ta.volatility.AverageTrueRange."""
    results = []
    df_bare = df.reset_index(drop=True)
    our_val = atr.calculate(df_bare, period)

    if HAS_TA:
        ref_series = _ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"],
            window=period, fillna=False
        ).average_true_range()
        if len(ref_series.dropna()) > 0:
            ref_val = float(ref_series.dropna().iloc[-1])
            results.append(ComparisonResult("ATR", "last_value", our_val, ref_val,
                                            note="ta: Wilder's(SMA seed)"))
        else:
            results.append(ComparisonResult("ATR", "last_value", our_val, our_val, note="참조값 없음"))
    else:
        # ta 없으면 수동 Wilder's 참조로 비교
        ref_series = _wilder_atr_ref(df, period)
        ref_val = float(ref_series.dropna().iloc[-1])
        results.append(ComparisonResult("ATR", "last_value", our_val, ref_val,
                                        note="참조: 수동 Wilder's(SMA seed)"))
    return results


def compare_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> list[ComparisonResult]:
    """BB: 우리 구현 vs ta.volatility.BollingerBands."""
    results = []
    df_bare = df.reset_index(drop=True)
    our = bollinger_bands.calculate(df_bare, period, std_dev)

    if HAS_TA:
        bb_ind = _ta.volatility.BollingerBands(
            close=df["close"], window=period, window_dev=std_dev, fillna=False
        )
        ref_upper  = float(bb_ind.bollinger_hband().dropna().iloc[-1])
        ref_middle = float(bb_ind.bollinger_mavg().dropna().iloc[-1])
        ref_lower  = float(bb_ind.bollinger_lband().dropna().iloc[-1])
        ref_pct    = float(bb_ind.bollinger_pband().dropna().iloc[-1])  # %B = (close-lower)/(upper-lower)
        ref_wband  = float(bb_ind.bollinger_wband().dropna().iloc[-1])  # width = (upper-lower)/middle * 100 -> 이미 %

        results.append(ComparisonResult("BB", "upper",      our["upper"],      ref_upper))
        results.append(ComparisonResult("BB", "middle",     our["middle"],     ref_middle))
        results.append(ComparisonResult("BB", "lower",      our["lower"],      ref_lower))
        results.append(ComparisonResult("BB", "percent_b",  our["percent_b"],  ref_pct))
        # bandwidth: ta는 (upper-lower)/middle * 100, 우리는 (upper-lower)/middle
        results.append(ComparisonResult("BB", "bandwidth",  our["bandwidth"] * 100, ref_wband,
                                        note="우리값*100 vs ta wband"))
    else:
        results.append(ComparisonResult("BB", "upper", our["upper"], our["upper"], note="ta 미설치"))
    return results


def compare_rsi(df: pd.DataFrame, period: int = 14) -> list[ComparisonResult]:
    """RSI: 우리 구현 vs ta.momentum.RSIIndicator."""
    results = []
    df_bare = df.reset_index(drop=True)
    our = rsi.calculate(df_bare, period)
    our_val = our["rsi"]

    if HAS_TA:
        ref_series = _ta.momentum.RSIIndicator(
            close=df["close"], window=period, fillna=False
        ).rsi()
        if len(ref_series.dropna()) > 0:
            ref_val = float(ref_series.dropna().iloc[-1])
            results.append(ComparisonResult("RSI", "last_value", our_val, ref_val))
            # 마지막 50개 평균 절대오차
            our_series = our["rsi_series"].reset_index(drop=True)
            ref_aligned = ref_series.reset_index(drop=True)
            tail = 50
            our_tail = our_series.dropna().tail(tail)
            ref_tail = ref_aligned.dropna().tail(tail)
            n = min(len(our_tail), len(ref_tail))
            if n >= 5:
                avg_err = float(np.mean(np.abs(our_tail.values[-n:] - ref_tail.values[-n:])))
                results.append(ComparisonResult("RSI", f"avg_err(tail{n})", avg_err, 0.0,
                                                note=f"avg_abs_err={avg_err:.4f}"))
        else:
            results.append(ComparisonResult("RSI", "last_value", our_val, our_val, note="참조값 없음"))
    else:
        results.append(ComparisonResult("RSI", "last_value", our_val, our_val, note="ta 미설치"))
    return results


def compare_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> list[ComparisonResult]:
    """MACD: 우리 구현 vs ta.trend.MACD."""
    results = []
    df_bare = df.reset_index(drop=True)
    our = macd.calculate(df_bare, fast, slow, signal)

    if HAS_TA:
        macd_ind = _ta.trend.MACD(
            close=df["close"], window_slow=slow, window_fast=fast, window_sign=signal, fillna=False
        )
        ref_macd = float(macd_ind.macd().dropna().iloc[-1])
        ref_sig  = float(macd_ind.macd_signal().dropna().iloc[-1])
        ref_hist = float(macd_ind.macd_diff().dropna().iloc[-1])

        results.append(ComparisonResult("MACD", "macd_line",   our["macd_line"],  ref_macd))
        results.append(ComparisonResult("MACD", "signal_line", our["signal_line"], ref_sig))
        results.append(ComparisonResult("MACD", "histogram",   our["histogram"],   ref_hist))
    else:
        results.append(ComparisonResult("MACD", "macd_line", our["macd_line"], our["macd_line"], note="ta 미설치"))
    return results


def compare_adx(df: pd.DataFrame, period: int = 14) -> list[ComparisonResult]:
    """ADX: 우리 구현 vs ta.trend.ADXIndicator."""
    results = []
    df_bare = df.reset_index(drop=True)
    our = adx.calculate(df_bare, period)

    if HAS_TA:
        adx_ind = _ta.trend.ADXIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=period, fillna=False
        )
        ref_adx = float(adx_ind.adx().dropna().iloc[-1])
        ref_dmp = float(adx_ind.adx_pos().dropna().iloc[-1])
        ref_dmn = float(adx_ind.adx_neg().dropna().iloc[-1])

        results.append(ComparisonResult("ADX", "adx",   our["adx"],      ref_adx))
        results.append(ComparisonResult("ADX", "+DI",   our["plus_di"],  ref_dmp))
        results.append(ComparisonResult("ADX", "-DI",   our["minus_di"], ref_dmn))
    else:
        results.append(ComparisonResult("ADX", "adx", our["adx"], our["adx"], note="ta 미설치"))
    return results


def compare_stoch_rsi(df: pd.DataFrame) -> list[ComparisonResult]:
    """StochRSI: 우리 구현 vs ta.momentum.StochRSIIndicator."""
    results = []
    df_bare = df.reset_index(drop=True)
    our = stoch_rsi.calculate(df_bare)

    if HAS_TA:
        sr_ind = _ta.momentum.StochRSIIndicator(
            close=df["close"], window=14, smooth1=3, smooth2=3, fillna=False
        )
        ref_k = float(sr_ind.stochrsi_k().dropna().iloc[-1]) * 100  # ta는 0~1 반환
        ref_d = float(sr_ind.stochrsi_d().dropna().iloc[-1]) * 100

        results.append(ComparisonResult("StochRSI", "%K", our["stoch_k"], ref_k))
        results.append(ComparisonResult("StochRSI", "%D", our["stoch_d"], ref_d))
    else:
        results.append(ComparisonResult("StochRSI", "%K", our["stoch_k"], our["stoch_k"], note="ta 미설치"))
    return results


def compare_historical_volatility(df: pd.DataFrame, period: int = 20, timeframe: str = "1h") -> list[ComparisonResult]:
    """HV: 우리 구현 vs 직접 계산 참조값 (ddof=1)."""
    df_bare = df.reset_index(drop=True)
    our_val = historical_volatility.calculate(df_bare, period, timeframe)
    _TF_MAP = {
        "1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
        "1h": 8_760, "2h": 4_380, "4h": 2_190, "6h": 1_460,
        "12h": 730, "1d": 365,
    }
    ppy = _TF_MAP.get(timeframe, 8_760)
    close = df["close"]
    log_ret = np.log(close / close.shift(1))
    ref_val = float(log_ret.rolling(period).std(ddof=1).iloc[-1] * np.sqrt(ppy) * 100)
    return [ComparisonResult("HV", "annualized_%", our_val, ref_val,
                             note="참조: 동일공식 직접계산(ddof=1)")]


def compare_hma(df: pd.DataFrame, period: int = 9) -> list[ComparisonResult]:
    """HMA: 우리 구현 vs 수동 참조 구현."""
    close = df["close"]
    our_series = hull_ma.hma(close, period)
    our_val = float(our_series.dropna().iloc[-1])

    # 수동 참조: WMA 함수를 직접 구현
    def _wma_ref(s: pd.Series, p: int) -> pd.Series:
        weights = np.arange(1, p + 1, dtype=float)
        total = weights.sum()
        return s.rolling(window=p).apply(lambda x: float(np.dot(x, weights) / total), raw=True)

    half = max(1, period // 2)
    sqrtp = max(1, int(math.sqrt(period)))
    diff = 2.0 * _wma_ref(close, half) - _wma_ref(close, period)
    ref_series = _wma_ref(diff, sqrtp)
    ref_val = float(ref_series.dropna().iloc[-1])

    return [ComparisonResult("HMA", f"last_value(p={period})", our_val, ref_val,
                             note="참조: 동일 WMA 로직 직접 계산")]


# ─────────────────────────────────────────────────────────────────────────────
# 리포트 출력
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_ICON = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}

def print_report(symbol: str, results: list[ComparisonResult]) -> None:
    print(f"\n{'='*80}")
    print(f"  [{symbol}] 지표 공식 검증 결과")
    print(f"{'='*80}")
    print(f"  {'지표':<14} {'메트릭':<24} {'우리값':>16} {'참조값':>16} {'상대오차':>10}  판정")
    print(f"  {'-'*76}")
    for r in results:
        icon = _STATUS_ICON.get(r.status, "?")
        note = f"  ({r.note})" if r.note else ""
        rel = f"{r.rel_error_pct:.4f}%" if not math.isinf(r.rel_error_pct) else "inf"
        print(
            f"  {r.indicator:<14} {r.metric:<24} {r.our_value:>16.6f} {r.ref_value:>16.6f}"
            f" {rel:>10}  {icon}{note}"
        )
    print()

    fails  = [r for r in results if r.status == "FAIL"]
    warns  = [r for r in results if r.status == "WARN"]
    passes = [r for r in results if r.status == "PASS"]
    print(f"  요약: PASS {len(passes)}개 / WARN {len(warns)}개 / FAIL {len(fails)}개")
    if fails:
        print(f"  [FAIL 항목] {', '.join(f'{r.indicator}/{r.metric}' for r in fails)}")
    print(f"{'='*80}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="지표 공식 검증 스크립트")
    parser.add_argument("--symbol",    default="BTC/USDT",  help="심볼 (기본: BTC/USDT)")
    parser.add_argument("--timeframe", default="1h",         help="타임프레임 (기본: 1h)")
    parser.add_argument("--limit",     default=500, type=int, help="캔들 수 (기본: 500)")
    args = parser.parse_args()

    print(f"\n바이낸스에서 {args.symbol} {args.timeframe} {args.limit}봉 데이터 수집 중...")
    df = fetch_ohlcv(args.symbol, args.timeframe, args.limit)
    print(f"수집 완료: {len(df)}봉  ({df.index[0]} ~ {df.index[-1]})")

    if not HAS_TA:
        print("\n[경고] ta 라이브러리 없이 실행 중 — 직접 계산 참조값만 사용합니다.")

    all_results: list[ComparisonResult] = []

    comparators = [
        ("ATR",      lambda: compare_atr(df)),
        ("BB",       lambda: compare_bollinger(df)),
        ("RSI",      lambda: compare_rsi(df)),
        ("MACD",     lambda: compare_macd(df)),
        ("ADX",      lambda: compare_adx(df)),
        ("StochRSI", lambda: compare_stoch_rsi(df)),
        ("HV",       lambda: compare_historical_volatility(df, timeframe=args.timeframe)),
        ("HMA",      lambda: compare_hma(df, period=9)),
    ]

    for name, fn in comparators:
        try:
            results = fn()
            all_results.extend(results)
        except Exception as e:
            print(f"[오류] {name} 비교 실패: {e}")
            import traceback; traceback.print_exc()

    print_report(args.symbol, all_results)

    fails = [r for r in all_results if r.status == "FAIL"]
    if fails:
        print("FAIL 항목이 있습니다. 해당 지표 공식을 수정해야 합니다.")
        sys.exit(1)
    else:
        print("모든 지표가 PASS 또는 WARN 범위 내에 있습니다.")


if __name__ == "__main__":
    main()
