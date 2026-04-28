"""
종합 자동 백테스트 서비스

매크로 점수(research_analyzer)와 기술적 점수(RSI/MACD/BB/ADX)를 합산한
롱/숏 독립 점수를 기반으로 진입/청산 신호를 생성하고
지정 기간 내 백테스트 결과를 반환한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class CompositeBacktestParams:
    symbol: str = "BTC/USDT"          # ccxt 포맷 (BTC/USDT)
    interval: str = "1h"              # "1h" | "4h" | "1d"
    start_date: str = ""              # "2024-01-01"
    end_date: str = ""                # "2024-06-30"
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 5.0
    initial_capital: float = 10000.0
    long_threshold: float = 70.0
    short_threshold: float = 70.0
    leverage: float = 1.0
    position_size_pct: float = 100.0
    score_exit_buffer: float = 15.0
    # ── 자동 튜닝용 가중치 (모두 None이면 기존 단순 평균 = 100% backwards-compat) ──
    macro_weight: float = 0.4         # 매크로/기술 비율 (기존 0.4 고정과 동일 default)
    tech_weight_rsi: float | None = None
    tech_weight_macd: float | None = None
    tech_weight_bb: float | None = None
    tech_weight_adx: float | None = None
    # Phase 1: 신규 5개 기술 지표 가중치 (모두 None이면 미사용 = backwards-compat)
    tech_weight_obv: float | None = None
    tech_weight_mfi: float | None = None
    tech_weight_vwap: float | None = None
    tech_weight_volume_spike: float | None = None
    tech_weight_stoch_rsi: float | None = None
    # Phase 2: 파생 신호 (OI + Funding Rate) 가중치. 0.0이면 미사용 = backwards-compat
    derivatives_weight: float = 0.0

    def __post_init__(self):
        if self.stop_loss_pct <= 0:
            raise ValueError(f"stop_loss_pct must be > 0, got {self.stop_loss_pct}")
        if self.take_profit_pct <= 0:
            raise ValueError(f"take_profit_pct must be > 0, got {self.take_profit_pct}")
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be > 0, got {self.initial_capital}")
        if self.leverage <= 0 or self.leverage > 100:
            raise ValueError(f"leverage must be > 0 and <= 100, got {self.leverage}")
        if self.position_size_pct <= 0 or self.position_size_pct > 100:
            raise ValueError(
                f"position_size_pct must be > 0 and <= 100, got {self.position_size_pct}"
            )
        if not (0 < self.long_threshold <= 100):
            raise ValueError(f"long_threshold must be in (0, 100], got {self.long_threshold}")
        if not (0 < self.short_threshold <= 100):
            raise ValueError(f"short_threshold must be in (0, 100], got {self.short_threshold}")
        if not (0 <= self.score_exit_buffer < 100):
            raise ValueError("score_exit_buffer는 0 이상 100 미만이어야 합니다")
        if self.score_exit_buffer >= self.long_threshold:
            raise ValueError(
                f"score_exit_buffer({self.score_exit_buffer})는 long_threshold({self.long_threshold})보다 작아야 합니다"
            )
        if self.score_exit_buffer >= self.short_threshold:
            raise ValueError(
                f"score_exit_buffer({self.score_exit_buffer})는 short_threshold({self.short_threshold})보다 작아야 합니다"
            )


# ---------------------------------------------------------------------------
# 심볼 포맷 변환 (BTCUSDT → BTC/USDT)
# ---------------------------------------------------------------------------

_KNOWN_QUOTES = ["USDT", "BTC", "ETH", "BNB", "BUSD", "USDC"]

# 인터벌별 밀리초 단위 캔들 크기
_INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _normalize_symbol(symbol: str) -> str:
    """API 입력 심볼을 ccxt 포맷으로 변환.

    "BTCUSDT" → "BTC/USDT", "BTC/USDT" → "BTC/USDT" (그대로)
    """
    if "/" in symbol:
        return symbol.upper()
    s = symbol.upper()
    for quote in _KNOWN_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"
    # 변환 불가 시 그대로 반환
    return s


# ---------------------------------------------------------------------------
# 점수 계산 함수들
# ---------------------------------------------------------------------------

def calc_macro_bullish_score(level: str) -> float:
    """매크로 레벨 문자열을 강세 점수(0~100)로 변환한다."""
    return {
        "bullish": 80.0,
        "neutral": 55.0,
        "bearish": 35.0,
        "warning": 20.0,
        "critical": 10.0,
    }.get(level, 50.0)


def calc_tech_bullish_score(
    details: dict,
    weights: dict[str, float] | None = None,
) -> float:
    """RSI·MACD·BB·ADX 세부 지표를 강세 점수로 변환 후 (가중)평균을 반환한다.

    details 구조:
      - "rsi": float or None
      - "macd": {"histogram": float, "prev_histogram": float} or None
      - "bb": float (0~1, %B) or None
      - "adx": {"adx": float, "plus_di": float, "minus_di": float} or None

    weights:
      - None (default): 기존 단순 평균 동작 유지 (backwards-compat)
      - dict: {"rsi": w_rsi, "macd": w_macd, "bb": w_bb, "adx": w_adx} 키별 가중치
              사용 가능한 지표만으로 정규화하여 가중평균 계산.
              모든 가중치가 0이거나 양수만 허용 (음수 시 단순 평균으로 fallback).

    유효한 지표가 하나도 없으면 50 반환.
    """
    indicator_scores: dict[str, float] = {}

    # RSI
    rsi_val = details.get("rsi")
    if rsi_val is not None:
        if rsi_val < 30:
            indicator_scores["rsi"] = 85.0   # 과매도
        elif rsi_val < 50:
            indicator_scores["rsi"] = 60.0   # 중립~약한 강세
        elif rsi_val < 70:
            indicator_scores["rsi"] = 45.0   # 중립
        else:
            indicator_scores["rsi"] = 20.0   # 과매수

    # MACD
    macd_val = details.get("macd")
    if macd_val is not None:
        hist = macd_val.get("histogram")
        prev_hist = macd_val.get("prev_histogram")
        if hist is not None and prev_hist is not None:
            if hist > 0 and hist > prev_hist:
                indicator_scores["macd"] = 75.0   # 상향 확대
            elif hist > 0:
                indicator_scores["macd"] = 55.0
            elif hist < 0 and hist < prev_hist:
                indicator_scores["macd"] = 25.0   # 하향 확대
            else:
                indicator_scores["macd"] = 45.0

    # BB (%B, 0~1)
    bb_val = details.get("bb")
    if bb_val is not None:
        if bb_val < 0.2:
            indicator_scores["bb"] = 80.0   # 하단 근접
        elif bb_val < 0.4:
            indicator_scores["bb"] = 60.0
        elif bb_val < 0.6:
            indicator_scores["bb"] = 45.0
        else:
            indicator_scores["bb"] = 25.0   # 상단 근접

    # ADX
    adx_val = details.get("adx")
    if adx_val is not None:
        adx = adx_val.get("adx", 0.0)
        plus_di = adx_val.get("plus_di", 0.0)
        minus_di = adx_val.get("minus_di", 0.0)
        if adx > 25 and plus_di > minus_di:
            indicator_scores["adx"] = 70.0   # 강한 상승 추세
        elif adx > 25:
            indicator_scores["adx"] = 30.0   # 강한 하락 추세
        else:
            indicator_scores["adx"] = 50.0   # 추세 약함

    # ── Phase 1: 신규 5개 지표 (long bias 점수) ──

    # OBV slope (%): 매집(>0) = long, 분배(<0) = short
    obv_slope = details.get("obv_slope")
    if obv_slope is not None:
        if obv_slope > 5.0:
            indicator_scores["obv"] = 75.0
        elif obv_slope > 0:
            indicator_scores["obv"] = 60.0
        elif obv_slope > -5.0:
            indicator_scores["obv"] = 40.0
        else:
            indicator_scores["obv"] = 25.0

    # MFI (0~100): 과매도일수록 long bias (RSI와 동일 패턴, 거래량 가중)
    mfi_val = details.get("mfi")
    if mfi_val is not None:
        if mfi_val < 20:
            indicator_scores["mfi"] = 85.0
        elif mfi_val < 50:
            indicator_scores["mfi"] = 60.0
        elif mfi_val < 80:
            indicator_scores["mfi"] = 40.0
        else:
            indicator_scores["mfi"] = 20.0

    # VWAP deviation %: 음수(저평가) = long bias
    vwap_dev = details.get("vwap_dev")
    if vwap_dev is not None:
        if vwap_dev < -3.0:
            indicator_scores["vwap"] = 80.0   # deeply below VWAP
        elif vwap_dev < -1.0:
            indicator_scores["vwap"] = 65.0
        elif vwap_dev < 1.0:
            indicator_scores["vwap"] = 50.0
        elif vwap_dev < 3.0:
            indicator_scores["vwap"] = 35.0
        else:
            indicator_scores["vwap"] = 20.0   # extended above

    # Volume Spike + 가격 변화 부호: spike 강할수록 가격 방향 신호 강화
    vol_spike = details.get("volume_spike")
    close_diff = details.get("close_diff")
    if vol_spike is not None and close_diff is not None:
        is_up = close_diff > 0
        if vol_spike > 2.0:
            indicator_scores["volume_spike"] = 80.0 if is_up else 20.0
        elif vol_spike > 1.5:
            indicator_scores["volume_spike"] = 65.0 if is_up else 35.0
        else:
            indicator_scores["volume_spike"] = 50.0   # neutral

    # Stoch RSI K (0~100): RSI와 동일 패턴, 단기 모멘텀 전환
    stoch_k = details.get("stoch_rsi_k")
    if stoch_k is not None:
        if stoch_k < 20:
            indicator_scores["stoch_rsi"] = 85.0
        elif stoch_k < 50:
            indicator_scores["stoch_rsi"] = 60.0
        elif stoch_k < 80:
            indicator_scores["stoch_rsi"] = 40.0
        else:
            indicator_scores["stoch_rsi"] = 20.0

    if not indicator_scores:
        return 50.0

    # weights=None → 기존 4개 지표(rsi/macd/bb/adx)만 단순 평균 (backwards-compat)
    # Phase 1 신규 5개 지표는 weights dict 명시 시에만 활성화
    if weights is None:
        legacy_keys = {"rsi", "macd", "bb", "adx"}
        legacy_scores = {k: v for k, v in indicator_scores.items() if k in legacy_keys}
        if not legacy_scores:
            return 50.0
        return sum(legacy_scores.values()) / len(legacy_scores)

    # 가중평균: indicator_scores에 있고 weights에서 양의 가중치를 가진 지표만 사용
    available_weights = {
        k: max(0.0, float(weights.get(k, 0.0))) for k in indicator_scores
    }
    total_weight = sum(available_weights.values())
    if total_weight <= 0:
        # 가중치 모두 0 → fallback: 4개 legacy 단순 평균
        legacy_keys = {"rsi", "macd", "bb", "adx"}
        legacy_scores = {k: v for k, v in indicator_scores.items() if k in legacy_keys}
        if not legacy_scores:
            return 50.0
        return sum(legacy_scores.values()) / len(legacy_scores)

    return sum(
        indicator_scores[k] * available_weights[k] for k in indicator_scores
    ) / total_weight


def calc_tech_bearish_score(
    details: dict,
    weights: dict[str, float] | None = None,
) -> float:
    """RSI·MACD·BB·ADX 세부 지표를 약세(숏) 점수로 변환 후 (가중)평균을 반환한다.

    weights 의미는 calc_tech_bullish_score와 동일.
    유효한 지표가 하나도 없으면 50 반환.
    """
    indicator_scores: dict[str, float] = {}

    # RSI: 과매수일수록 숏 강세
    rsi_val = details.get("rsi")
    if rsi_val is not None:
        if rsi_val > 70:
            indicator_scores["rsi"] = 85.0   # 과매수 = 숏 강세
        elif rsi_val > 55:
            indicator_scores["rsi"] = 65.0
        elif rsi_val > 40:
            indicator_scores["rsi"] = 45.0
        else:
            indicator_scores["rsi"] = 20.0   # 과매도

    # MACD: 하향 확대일수록 숏 강세
    macd_val = details.get("macd")
    if macd_val is not None:
        hist = macd_val.get("histogram")
        prev_hist = macd_val.get("prev_histogram")
        if hist is not None and prev_hist is not None:
            if hist < 0 and hist < prev_hist:
                indicator_scores["macd"] = 75.0   # 하향 확대
            elif hist < 0:
                indicator_scores["macd"] = 55.0
            elif hist > 0 and hist > prev_hist:
                indicator_scores["macd"] = 25.0   # 상향 확대
            else:
                indicator_scores["macd"] = 45.0

    # BB %B: 상단 근접일수록 숏 강세
    bb_val = details.get("bb")
    if bb_val is not None:
        if bb_val > 0.8:
            indicator_scores["bb"] = 80.0   # 상단 근접 = 숏 강세
        elif bb_val > 0.6:
            indicator_scores["bb"] = 60.0
        elif bb_val > 0.4:
            indicator_scores["bb"] = 45.0
        else:
            indicator_scores["bb"] = 25.0

    # ADX: 강한 하락 추세일수록 숏 강세
    adx_val = details.get("adx")
    if adx_val is not None:
        adx = adx_val.get("adx", 0.0)
        plus_di = adx_val.get("plus_di", 0.0)
        minus_di = adx_val.get("minus_di", 0.0)
        if adx > 25 and minus_di > plus_di:
            indicator_scores["adx"] = 70.0   # 강한 하락 추세
        elif adx > 25:
            indicator_scores["adx"] = 30.0
        else:
            indicator_scores["adx"] = 50.0

    # ── Phase 1: 신규 5개 지표 (short bias 점수, long의 mirror) ──

    # OBV slope: 분배(<0) = short bias
    obv_slope = details.get("obv_slope")
    if obv_slope is not None:
        if obv_slope < -5.0:
            indicator_scores["obv"] = 75.0
        elif obv_slope < 0:
            indicator_scores["obv"] = 60.0
        elif obv_slope < 5.0:
            indicator_scores["obv"] = 40.0
        else:
            indicator_scores["obv"] = 25.0

    # MFI: 과매수일수록 short bias
    mfi_val = details.get("mfi")
    if mfi_val is not None:
        if mfi_val > 80:
            indicator_scores["mfi"] = 85.0
        elif mfi_val > 50:
            indicator_scores["mfi"] = 60.0
        elif mfi_val > 20:
            indicator_scores["mfi"] = 40.0
        else:
            indicator_scores["mfi"] = 20.0

    # VWAP deviation: 양수(고평가) = short bias
    vwap_dev = details.get("vwap_dev")
    if vwap_dev is not None:
        if vwap_dev > 3.0:
            indicator_scores["vwap"] = 80.0
        elif vwap_dev > 1.0:
            indicator_scores["vwap"] = 65.0
        elif vwap_dev > -1.0:
            indicator_scores["vwap"] = 50.0
        elif vwap_dev > -3.0:
            indicator_scores["vwap"] = 35.0
        else:
            indicator_scores["vwap"] = 20.0

    # Volume Spike + 가격 변화 부호: spike + 가격 하락 = short bias 강화
    vol_spike = details.get("volume_spike")
    close_diff = details.get("close_diff")
    if vol_spike is not None and close_diff is not None:
        is_down = close_diff < 0
        if vol_spike > 2.0:
            indicator_scores["volume_spike"] = 80.0 if is_down else 20.0
        elif vol_spike > 1.5:
            indicator_scores["volume_spike"] = 65.0 if is_down else 35.0
        else:
            indicator_scores["volume_spike"] = 50.0

    # Stoch RSI K: 과매수일수록 short bias
    stoch_k = details.get("stoch_rsi_k")
    if stoch_k is not None:
        if stoch_k > 80:
            indicator_scores["stoch_rsi"] = 85.0
        elif stoch_k > 50:
            indicator_scores["stoch_rsi"] = 60.0
        elif stoch_k > 20:
            indicator_scores["stoch_rsi"] = 40.0
        else:
            indicator_scores["stoch_rsi"] = 20.0

    if not indicator_scores:
        return 50.0

    # weights=None → 기존 4개만 단순 평균 (backwards-compat)
    if weights is None:
        legacy_keys = {"rsi", "macd", "bb", "adx"}
        legacy_scores = {k: v for k, v in indicator_scores.items() if k in legacy_keys}
        if not legacy_scores:
            return 50.0
        return sum(legacy_scores.values()) / len(legacy_scores)

    available_weights = {
        k: max(0.0, float(weights.get(k, 0.0))) for k in indicator_scores
    }
    total_weight = sum(available_weights.values())
    if total_weight <= 0:
        legacy_keys = {"rsi", "macd", "bb", "adx"}
        legacy_scores = {k: v for k, v in indicator_scores.items() if k in legacy_keys}
        if not legacy_scores:
            return 50.0
        return sum(legacy_scores.values()) / len(legacy_scores)

    return sum(
        indicator_scores[k] * available_weights[k] for k in indicator_scores
    ) / total_weight


def calc_long_score(
    macro_bullish: float,
    tech_details: dict,
    macro_weight: float = 0.4,
    tech_weights: dict[str, float] | None = None,
) -> float:
    """매크로 강세 + 기술적 강세 점수를 macro_weight 비율로 합산해 롱 점수를 반환한다.

    macro_weight=0.4 (default) → 매크로 0.4 + 기술 0.6 (기존 고정 비율과 동등).
    tech_weights=None (default) → 기술 점수는 4개 지표 단순 평균 (기존 동작).
    """
    macro_weight = max(0.0, min(1.0, float(macro_weight)))
    tech_weight = 1.0 - macro_weight
    tech_score = calc_tech_bullish_score(tech_details, tech_weights)
    return macro_bullish * macro_weight + tech_score * tech_weight


def calc_short_score(
    macro_bullish: float,
    tech_details: dict,
    macro_weight: float = 0.4,
    tech_weights: dict[str, float] | None = None,
) -> float:
    """매크로 약세 + 기술적 약세 점수를 macro_weight 비율로 합산해 숏 점수를 반환한다.

    인자 의미는 calc_long_score와 동일. macro_weight는 양쪽에 동일 비율 적용.
    """
    macro_weight = max(0.0, min(1.0, float(macro_weight)))
    tech_weight = 1.0 - macro_weight
    macro_bearish = 100.0 - macro_bullish
    tech_score = calc_tech_bearish_score(tech_details, tech_weights)
    return macro_bearish * macro_weight + tech_score * tech_weight


# ---------------------------------------------------------------------------
# 전체 DataFrame 기반 지표 일괄 계산 (O(n) 최적화)
# ---------------------------------------------------------------------------

def _safe_float(series: pd.Series, loc) -> float | None:
    """Series에서 loc 위치 값을 안전하게 float으로 반환한다."""
    try:
        val = series.loc[loc]
        return None if pd.isna(val) else float(val)
    except Exception:
        return None


def _compute_all_indicators(full_df: pd.DataFrame) -> dict[str, pd.Series]:
    """전체 OHLCV DataFrame에 대해 9개 지표를 한 번만 계산 후 Series 반환.

    기존 4개: RSI, MACD, BB, ADX (변경 없음)
    신규 5개 (Phase 1): OBV slope, MFI, VWAP deviation %, Volume Spike, Stoch RSI K
    """
    close = full_df["close"]
    high = full_df["high"]
    low = full_df["low"]
    volume = full_df["volume"]

    # RSI (14 period)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi_series = 100 - 100 / (1 + rs)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram_series = macd_line - signal_line
    prev_histogram_series = histogram_series.shift(1)

    # BB %B (20 period)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = sma20 + 2 * std20
    lower_band = sma20 - 2 * std20
    band_width = upper - lower_band
    bb_series = (close - lower_band) / band_width.replace(0, float("nan"))

    # ADX (14 period)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
    plus_di_series = 100 * plus_dm.rolling(14).mean() / atr
    minus_di_series = 100 * minus_dm.rolling(14).mean() / atr
    dx = (
        (plus_di_series - minus_di_series).abs()
        / (plus_di_series + minus_di_series).replace(0, float("nan"))
        * 100
    )
    adx_series = dx.rolling(14).mean()

    # ── Phase 1: 신규 5개 지표 ──
    typical_price = (high + low + close) / 3.0

    # OBV slope (14봉 변화율 %): 양수=매집, 음수=분배
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv_series_full = (volume * direction).cumsum()
    obv_slope_series = obv_series_full.diff(14) / obv_series_full.shift(14).abs().replace(0, float("nan")) * 100

    # MFI (14 period, 0~100)
    money_flow = typical_price * volume
    tp_diff = typical_price.diff()
    positive_mf = money_flow.where(tp_diff > 0, 0.0)
    negative_mf = money_flow.where(tp_diff < 0, 0.0)
    pos_sum_mfi = positive_mf.rolling(14).sum()
    neg_sum_mfi = negative_mf.rolling(14).sum()
    mfi_ratio = pos_sum_mfi / neg_sum_mfi.replace(0, float("nan"))
    mfi_series = 100 - 100 / (1 + mfi_ratio)

    # VWAP deviation % (20 period rolling): (현재가 - VWAP) / VWAP × 100
    tp_vol = typical_price * volume
    vwap_series = tp_vol.rolling(20).sum() / volume.rolling(20).sum()
    vwap_dev_series = (close - vwap_series) / vwap_series.replace(0, float("nan")) * 100

    # Volume Spike (현재 봉 거래량 / 20봉 평균)
    vol_mean20 = volume.rolling(20).mean()
    volume_spike_series = volume / vol_mean20.replace(0, float("nan"))

    # Stoch RSI K (14 RSI + 14 stoch period, 3 SMA smoothing)
    stoch_min = rsi_series.rolling(14).min()
    stoch_max = rsi_series.rolling(14).max()
    stoch_raw = (rsi_series - stoch_min) / (stoch_max - stoch_min).replace(0, float("nan")) * 100
    stoch_rsi_k_series = stoch_raw.rolling(3).mean()

    # ── Regime detection: 4주(1h봉=672) MA 우상향 + ADX > 30 = 강한 상승 추세 ──
    # 4주 MA의 현재값 vs 이전 168봉(1주) 전 값 비교 → 우상향 여부
    INTERVAL_4W = 672  # 1h봉 기준 4주 = 28일 × 24시간
    ma_4w_series = close.rolling(INTERVAL_4W, min_periods=INTERVAL_4W // 2).mean()
    # 1주 전 4주 MA 대비 변화 — 양수면 4주 MA 우상향
    ma_4w_slope_series = ma_4w_series.diff(168)  # 1주 = 168봉
    # regime: True = strong_bull (4주 MA 우상향 + ADX > 30)
    regime_strong_bull_series = (ma_4w_slope_series > 0) & (adx_series > 30)

    return {
        "rsi": rsi_series,
        "histogram": histogram_series,
        "prev_histogram": prev_histogram_series,
        "bb": bb_series,
        "adx": adx_series,
        "plus_di": plus_di_series,
        "minus_di": minus_di_series,
        # Phase 1 신규
        "obv_slope": obv_slope_series,
        "mfi": mfi_series,
        "vwap_dev": vwap_dev_series,
        "volume_spike": volume_spike_series,
        "stoch_rsi_k": stoch_rsi_k_series,
        # 가격 변화 부호 (Volume Spike 방향성용)
        "close_diff": close.diff(),
        # Regime detection (Phase 4: 강세장 = 시스템 OFF)
        "regime_strong_bull": regime_strong_bull_series,
    }


# ---------------------------------------------------------------------------
# 동기 내부 함수 (스레드 풀에서 실행)
# ---------------------------------------------------------------------------

def _fetch_ohlcv(params: CompositeBacktestParams) -> pd.DataFrame | None:
    """DataCollector._get_exchange()로 OHLCV를 수집해 datetime 인덱스 DataFrame을 반환한다.

    start_date 기준 워밍업 200봉 이전 시점부터 end_date까지 페이지네이션으로 전체 수집.
    """
    try:
        from app.data.data_collector import DataCollector

        collector = DataCollector()
        exchange = collector._get_exchange()
        ccxt_symbol = _normalize_symbol(params.symbol)
        interval_ms = _INTERVAL_MS.get(params.interval, 3_600_000)

        # since 계산: start_date에서 워밍업(200봉) 만큼 앞선 시점
        if params.start_date:
            start_ts_ms = int(pd.Timestamp(params.start_date, tz="UTC").timestamp() * 1000)
            since = start_ts_ms - 200 * interval_ms
        else:
            since = None

        end_ts_ms: int | None = None
        if params.end_date:
            end_ts_ms = int(pd.Timestamp(params.end_date, tz="UTC").timestamp() * 1000)

        # ccxt 한 번에 최대 1000봉 제한 — 페이지네이션으로 전체 기간 수집
        PAGE = 1000
        all_raw: list = []
        cur_since = since
        while True:
            batch = exchange.fetch_ohlcv(
                ccxt_symbol,
                timeframe=params.interval,
                limit=PAGE,
                since=cur_since,
            )
            if not batch:
                break
            all_raw.extend(batch)
            last_ts = batch[-1][0]
            # end_date를 초과했거나 배치가 꽉 차지 않으면 종료
            if end_ts_ms and last_ts >= end_ts_ms:
                break
            if len(batch) < PAGE:
                break
            cur_since = last_ts + interval_ms

        if not all_raw:
            logger.warning("OHLCV 데이터 없음: symbol=%s", ccxt_symbol)
            return None

        df = pd.DataFrame(all_raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime").drop(columns=["timestamp"])
        df = df[~df.index.duplicated(keep="last")].sort_index()
        # end_date 이후 봉 제거
        if end_ts_ms:
            df = df[df.index <= pd.Timestamp(params.end_date, tz="UTC")]
        return df

    except Exception as exc:
        logger.error("OHLCV 수집 실패: %s", exc, exc_info=True)
        return None


def _to_perp_symbol(ccxt_symbol: str) -> str:
    """spot 심볼(BTC/USDT)을 perpetual 심볼(BTC/USDT:USDT)로 변환."""
    if ":" in ccxt_symbol:
        return ccxt_symbol
    parts = ccxt_symbol.split("/")
    if len(parts) == 2:
        return f"{ccxt_symbol}:{parts[1]}"
    return ccxt_symbol


def _fetch_derivatives(
    params: CompositeBacktestParams,
    full_df_index: pd.DatetimeIndex,
) -> pd.DataFrame | None:
    """OI + Funding Rate 시계열을 ccxt에서 fetch 후 1h봉 align해서 DataFrame 반환.

    fetch 실패 시 None 반환 — 호출부에서 derivatives 비활성으로 처리.
    """
    try:
        from app.data.data_collector import DataCollector

        collector = DataCollector()
        exchange = collector._get_exchange()
        perp_symbol = _to_perp_symbol(_normalize_symbol(params.symbol))
        interval_ms = _INTERVAL_MS.get(params.interval, 3_600_000)

        # since 계산 (start_date - 워밍업 200봉)
        if params.start_date:
            start_ts_ms = int(pd.Timestamp(params.start_date, tz="UTC").timestamp() * 1000)
            since = start_ts_ms - 200 * interval_ms
        else:
            since = int(full_df_index[0].timestamp() * 1000)

        end_ts_ms = int(full_df_index[-1].timestamp() * 1000) + interval_ms

        # 1) OI 페이지네이션 (max 200/call)
        oi_data: list = []
        cur = since
        for _ in range(200):  # 최대 200 calls = 40000봉 안전 한도
            batch = exchange.fetch_open_interest_history(
                perp_symbol, timeframe=params.interval, limit=200, since=cur
            )
            if not batch:
                break
            oi_data.extend(batch)
            last_ts = batch[-1]["timestamp"]
            if last_ts >= end_ts_ms or len(batch) < 200:
                break
            cur = last_ts + interval_ms

        # 2) FR 페이지네이션 (8h 단위)
        fr_data: list = []
        cur = since
        for _ in range(200):
            batch = exchange.fetch_funding_rate_history(perp_symbol, limit=200, since=cur)
            if not batch:
                break
            fr_data.extend(batch)
            last_ts = batch[-1]["timestamp"]
            if last_ts >= end_ts_ms or len(batch) < 200:
                break
            cur = last_ts + 8 * 3_600_000

        if not oi_data or not fr_data:
            logger.warning(
                "Derivatives fetch 빈 결과: oi=%d fr=%d", len(oi_data), len(fr_data)
            )
            return None

        # 3) DataFrame 구성
        oi_rows = [
            {
                "datetime": pd.to_datetime(r["timestamp"], unit="ms", utc=True),
                "oi": float(r.get("openInterestAmount") or 0.0),
            }
            for r in oi_data
            if r.get("openInterestAmount") is not None
        ]
        fr_rows = [
            {
                "datetime": pd.to_datetime(r["timestamp"], unit="ms", utc=True),
                "funding_rate": float(r.get("fundingRate") or 0.0),
            }
            for r in fr_data
            if r.get("fundingRate") is not None
        ]
        if not oi_rows or not fr_rows:
            return None

        oi_df = pd.DataFrame(oi_rows).drop_duplicates("datetime").set_index("datetime").sort_index()
        fr_df = pd.DataFrame(fr_rows).drop_duplicates("datetime").set_index("datetime").sort_index()

        # full_df_index에 reindex + ffill (OHLCV 봉 시각으로 align)
        oi_aligned = oi_df["oi"].reindex(full_df_index, method="ffill")
        fr_aligned = fr_df["funding_rate"].reindex(full_df_index, method="ffill")

        return pd.DataFrame({"oi": oi_aligned, "funding_rate": fr_aligned})

    except Exception as exc:
        logger.warning("Derivatives fetch 실패: %s", exc)
        return None


def _compute_derivatives_signals(
    full_df: pd.DataFrame, deriv_df: pd.DataFrame | None
) -> dict[str, pd.Series] | None:
    """파생상품 데이터로부터 OI 3일 변화율 + funding rate 시계열을 계산한다.

    Args:
        full_df: OHLCV DataFrame (datetime index, UTC)
        deriv_df: 'oi', 'funding_rate' 컬럼 + 동일 인덱스 (1h봉으로 align됨)

    Returns:
        None: deriv_df가 None이면 derivatives 미사용
        dict: {'oi_chg_3d_pct': Series, 'funding_rate': Series} - full_df 인덱스에 매핑
    """
    if deriv_df is None or deriv_df.empty:
        return None

    # full_df 인덱스에 reindex + forward-fill (1h 단위 align)
    aligned = deriv_df.reindex(full_df.index).ffill()
    oi_series = aligned.get("oi")
    fr_series = aligned.get("funding_rate")

    if oi_series is None or fr_series is None:
        return None

    # OI 3일(72봉) 변화율 %
    interval_idx = full_df.index
    if len(interval_idx) >= 2:
        # 1h봉 → 3일 = 72개. 다른 interval은 비례 조정 (간단화: 1h만 우선 지원)
        oi_3d_ago = oi_series.shift(72)
        oi_chg_3d_pct = (oi_series - oi_3d_ago) / oi_3d_ago.replace(0, float("nan")) * 100
    else:
        oi_chg_3d_pct = pd.Series(0.0, index=full_df.index)

    return {
        "oi_chg_3d_pct": oi_chg_3d_pct,
        "funding_rate": fr_series,
    }


# 파생 신호 임계값 (DerivativesAnalyzer와 동일)
_DERIV_OI_SURGE_PCT = 12.0
_DERIV_FR_LONG_EXTREME = 0.000082
_DERIV_FR_SHORT_EXTREME = 0.0


def _calc_derivatives_score(
    oi_chg_pct: float | None, fr: float | None
) -> tuple[float, float, bool]:
    """OI 변화율 + funding rate로부터 (long_boost, short_boost, liquidation_risk) 반환.

    각 boost는 -100~+100 범위. 양수 = 해당 방향 진입에 가산점, 음수 = 차감.
    liquidation_risk=True 시 진입 차단해야 함.
    """
    if oi_chg_pct is None or fr is None:
        return 0.0, 0.0, False

    oi_surge = abs(oi_chg_pct) > _DERIV_OI_SURGE_PCT
    fr_short_crowded = fr < _DERIV_FR_SHORT_EXTREME    # 숏 쏠림 → 롱 우호
    fr_long_crowded = fr > _DERIV_FR_LONG_EXTREME      # 롱 쏠림 → 숏 우호
    fr_extreme = fr_short_crowded or fr_long_crowded

    # 청산 캐스케이드 위험: OI 급등 + FR 극단 동시 → 진입 차단
    liquidation_risk = oi_surge and fr_extreme

    long_boost = 0.0
    short_boost = 0.0

    # OI 급등 + 가격이 위로 → 추세 강화 (롱 우호) / OI 급등 + 가격 아래 → 숏 강화
    # 여기서 oi_chg_pct 부호로 추세 방향 추정 — 보수적 +/-15 가산
    if oi_surge:
        if oi_chg_pct > 0:
            long_boost += 15.0
        else:
            short_boost += 15.0

    # Funding 극단 = 역방향 신호 (쏠린 쪽이 청산되며 반대 방향 분출)
    if fr_short_crowded:
        long_boost += 10.0    # 숏 쏠림 → 숏 청산 시 가격 급등 가능 → 롱 가산
    if fr_long_crowded:
        short_boost += 10.0   # 롱 쏠림 → 롱 청산 시 가격 급락 가능 → 숏 가산

    return long_boost, short_boost, liquidation_risk


def _run_backtest_sync(
    full_df: pd.DataFrame,
    params: CompositeBacktestParams,
    macro_bullish: float,
    deriv_df: pd.DataFrame | None = None,
    macro_series: pd.Series | None = None,
) -> dict:
    """동기 백테스트 루프. 스레드 풀에서 실행된다.

    롱/숏 독립 점수 시스템, Flip, 레버리지, 수수료, 강제청산을 지원한다.

    deriv_df=None이면 derivatives 미적용 (기존 동작 유지). dict 형태로 'oi'/'funding_rate'
    컬럼이 있으면 derivatives_weight 비율로 long/short score에 가산.

    macro_series=None이면 macro_bullish 단일값 사용 (기존 동작). Series가 주어지면
    해당 시점의 매크로 점수로 동적 사용 (Phase 3).
    """

    FEE_RATE = 0.0006  # 0.06% 수수료

    # start_date / end_date 파싱
    start_ts = (
        pd.Timestamp(params.start_date, tz="UTC")
        if params.start_date
        else full_df.index[0]
    )
    end_ts = (
        pd.Timestamp(params.end_date, tz="UTC")
        if params.end_date
        else full_df.index[-1]
    )

    # 워밍업 최소 100개 캔들 보장
    warmup_min = 100

    # target 인덱스: start_ts ~ end_ts 범위 캔들
    target_mask = (full_df.index >= start_ts) & (full_df.index <= end_ts)
    target_indices = [i for i, v in enumerate(target_mask) if v]

    if not target_indices:
        return {"error": "지정 기간 내 데이터 없음 (start_date ~ end_date 범위 확인)"}

    # 첫 target 캔들 기준으로 최소 warmup_min개 선행 캔들 확보 여부 확인
    first_target_idx = target_indices[0]
    if first_target_idx < warmup_min:
        # 워밍업 부족 → target_indices 앞쪽 제거해 warmup_min 보장
        target_indices = [i for i in target_indices if i >= warmup_min]
        if not target_indices:
            return {"error": f"워밍업 캔들 부족: 최소 {warmup_min}개 선행 데이터 필요"}

    # 전체 DataFrame 기준으로 지표 일괄 계산 (O(n), 루프 외부)
    indicator_series = _compute_all_indicators(full_df)
    # Phase 2: 파생 시계열 (None이면 비활성)
    deriv_series = _compute_derivatives_signals(full_df, deriv_df)

    # ── 자동 튜닝 가중치 추출 (params에서 한 번만 빌드해 루프 내 재사용) ──
    # 9개 모두 None이면 tech_weights=None → 기존 단순 평균 동작 유지 (4개 legacy만 사용)
    weight_fields = {
        "rsi": params.tech_weight_rsi,
        "macd": params.tech_weight_macd,
        "bb": params.tech_weight_bb,
        "adx": params.tech_weight_adx,
        # Phase 1 신규
        "obv": params.tech_weight_obv,
        "mfi": params.tech_weight_mfi,
        "vwap": params.tech_weight_vwap,
        "volume_spike": params.tech_weight_volume_spike,
        "stoch_rsi": params.tech_weight_stoch_rsi,
    }
    if any(v is not None for v in weight_fields.values()):
        # 일부라도 지정되면 dict로 빌드. None은 0.0으로 간주.
        tech_weights: dict[str, float] | None = {
            k: (float(v) if v is not None else 0.0) for k, v in weight_fields.items()
        }
    else:
        tech_weights = None
    macro_weight = float(params.macro_weight)
    derivatives_weight = float(params.derivatives_weight)

    initial_capital = params.initial_capital
    capital = initial_capital
    position: dict | None = None
    trades: list[dict] = []
    equity_curve: list[dict] = []
    liquidated = False

    total_candles = len(target_indices)

    for seq, idx in enumerate(target_indices):
        candle_row = full_df.iloc[idx]
        loc = full_df.index[idx]
        ts_str = loc.isoformat()
        close = float(candle_row["close"])
        high = float(candle_row["high"])
        low = float(candle_row["low"])

        # 인덱스 조회만으로 지표값 추출 (재계산 없음)
        details = {
            "rsi": _safe_float(indicator_series["rsi"], loc),
            "macd": {
                "histogram": _safe_float(indicator_series["histogram"], loc),
                "prev_histogram": _safe_float(indicator_series["prev_histogram"], loc),
            },
            "bb": _safe_float(indicator_series["bb"], loc),
            "adx": {
                "adx": _safe_float(indicator_series["adx"], loc),
                "plus_di": _safe_float(indicator_series["plus_di"], loc),
                "minus_di": _safe_float(indicator_series["minus_di"], loc),
            },
            # Phase 1 신규
            "obv_slope": _safe_float(indicator_series["obv_slope"], loc),
            "mfi": _safe_float(indicator_series["mfi"], loc),
            "vwap_dev": _safe_float(indicator_series["vwap_dev"], loc),
            "volume_spike": _safe_float(indicator_series["volume_spike"], loc),
            "stoch_rsi_k": _safe_float(indicator_series["stoch_rsi_k"], loc),
            "close_diff": _safe_float(indicator_series["close_diff"], loc),
        }

        # Phase 3: macro_series가 주어지면 시점별 macro_score 사용, 아니면 단일값
        macro_now = (
            _safe_float(macro_series, loc)
            if macro_series is not None
            else None
        )
        if macro_now is None:
            macro_now = macro_bullish

        # 롱/숏 독립 점수 계산 (튜닝 가중치 적용; 기본값일 땐 기존 동작과 동등)
        long_score = calc_long_score(macro_now, details, macro_weight, tech_weights)
        short_score = calc_short_score(macro_now, details, macro_weight, tech_weights)

        # ── Phase 2: 파생 신호 가산 (deriv_series 있고 derivatives_weight > 0일 때만) ──
        liquidation_risk = False
        if deriv_series is not None and derivatives_weight > 0.0:
            oi_chg = _safe_float(deriv_series["oi_chg_3d_pct"], loc)
            fr = _safe_float(deriv_series["funding_rate"], loc)
            d_long, d_short, liquidation_risk = _calc_derivatives_score(oi_chg, fr)
            # derivatives_weight 비율로 가산 (음수 가산 방지를 위해 long/short_score는 결과를 0~100 cap)
            long_score = max(0.0, min(100.0, long_score + d_long * derivatives_weight))
            short_score = max(0.0, min(100.0, short_score + d_short * derivatives_weight))

        long_threshold = params.long_threshold
        short_threshold = params.short_threshold
        is_last = (seq == total_candles - 1)

        # ── Regime detection: 강세장 = 시스템 OFF (active short 차단, long-only hold) ──
        regime_strong_bull = bool(_safe_float(indicator_series["regime_strong_bull"], loc) or 0.0)

        # 양쪽 동시 트리거 여부
        both_triggered = (long_score > long_threshold) and (short_score > short_threshold)

        if position is None:
            # ── 포지션 없을 때: 진입 판단 ──
            if liquidation_risk:
                # Phase 2: OI 급등 + Funding 극단 동시 → 청산 캐스케이드 위험 → 진입 차단
                pass
            elif both_triggered:
                # 양쪽 모두 트리거 → 관망
                pass
            elif long_score > long_threshold and macro_now >= 40:
                # 롱 진입 (bearish 매크로 = macro_now < 40 시 차단)
                size = params.position_size_pct / 100.0
                allocated = capital * size
                entry_fee = allocated * FEE_RATE
                capital -= entry_fee
                position = {
                    "direction": "long",
                    "entry_price": close,
                    "entry_timestamp": ts_str,
                    "allocated": allocated,
                    "long_score": long_score,
                    "short_score": short_score,
                }
                trades.append({
                    "type": "entry",
                    "direction": "long",
                    "timestamp": ts_str,
                    "price": close,
                    "pnl_pct": None,
                    "reason": None,
                    "long_score": round(long_score, 2),
                    "short_score": round(short_score, 2),
                })
            elif short_score > short_threshold and not regime_strong_bull:
                # 숏 진입 — 강세장(regime_strong_bull)에서는 차단
                size = params.position_size_pct / 100.0
                allocated = capital * size
                entry_fee = allocated * FEE_RATE
                capital -= entry_fee
                position = {
                    "direction": "short",
                    "entry_price": close,
                    "entry_timestamp": ts_str,
                    "allocated": allocated,
                    "long_score": long_score,
                    "short_score": short_score,
                }
                trades.append({
                    "type": "entry",
                    "direction": "short",
                    "timestamp": ts_str,
                    "price": close,
                    "pnl_pct": None,
                    "reason": None,
                    "long_score": round(long_score, 2),
                    "short_score": round(short_score, 2),
                })

        else:
            # ── 포지션 있을 때: 청산 판단 ──
            direction = position["direction"]
            entry = position["entry_price"]
            reason: str | None = None

            exit_price = close  # 기본값: 종가 체결

            # 1순위: 손절 (SL) — 저가/고가로 체크, SL 정확한 가격에 체결
            # 동일 캔들에서 SL·TP 동시 발생 시 SL 우선 (보수적 백테스트 원칙)
            sl_pct = params.stop_loss_pct / 100
            tp_pct = params.take_profit_pct / 100

            if direction == "long":
                sl_price = entry * (1 - sl_pct)
                tp_price = entry * (1 + tp_pct)
                if low <= sl_price:
                    reason = "stop_loss"
                    exit_price = sl_price
                elif high >= tp_price:
                    reason = "take_profit"
                    exit_price = tp_price
            else:  # short
                sl_price = entry * (1 + sl_pct)
                tp_price = entry * (1 - tp_pct)
                if high >= sl_price:
                    reason = "stop_loss"
                    exit_price = sl_price
                elif low <= tp_price:
                    reason = "take_profit"
                    exit_price = tp_price

            # 3순위: Flip (반대 방향 신호 강함)
            #   강세장(regime_strong_bull): long → short flip 차단 (홀딩 강제)
            if reason is None:
                if direction == "long" and short_score > short_threshold and not both_triggered:
                    if not regime_strong_bull:
                        reason = "flip"
                elif direction == "short" and long_score > long_threshold and not both_triggered:
                    reason = "flip"

            # 4순위: 점수 하락 (score_exit) — buffer만큼 여유 부여
            #   강세장: long → score_exit 차단 (홀딩 강제). short는 강세장이면 강제 청산.
            if reason is None:
                exit_long = long_threshold - params.score_exit_buffer
                exit_short = short_threshold - params.score_exit_buffer
                if direction == "long" and long_score <= exit_long:
                    if not regime_strong_bull:
                        reason = "score_exit"
                elif direction == "short" and short_score <= exit_short:
                    reason = "score_exit"

            # 추가 5순위: 강세장 진입 시 short 포지션 즉시 청산 (잘못된 방향)
            if reason is None and direction == "short" and regime_strong_bull:
                reason = "regime_short_force_close"

            # 5순위: 기간 종료
            if reason is None and is_last:
                reason = "period_end"

            if reason:
                # ── 청산 실행 ──
                if direction == "long":
                    raw_return = (exit_price - entry) / entry
                else:  # short
                    raw_return = (entry - exit_price) / entry

                pnl_pct = raw_return * params.leverage * 100

                # 포지션 allocated 기준으로 손익 및 청산 수수료 계산
                pos_allocated = position["allocated"]
                pnl_amount = pos_allocated * (pnl_pct / 100.0)
                exit_fee = pos_allocated * FEE_RATE
                capital += pnl_amount - exit_fee

                # 강제청산 확인
                if capital <= 0:
                    capital = 0.0
                    liquidated = True
                    trades.append({
                        "type": "exit",
                        "direction": direction,
                        "timestamp": ts_str,
                        "price": exit_price,
                        "pnl_pct": round(pnl_pct, 4),
                        "reason": "liquidated",
                        "long_score": round(long_score, 2),
                        "short_score": round(short_score, 2),
                    })
                    equity_curve.append({
                        "timestamp": ts_str,
                        "value": 0.0,
                    })
                    position = None
                    break

                trades.append({
                    "type": "exit",
                    "direction": direction,
                    "timestamp": ts_str,
                    "price": exit_price,
                    "pnl_pct": round(pnl_pct, 4),
                    "reason": reason,
                    "long_score": round(long_score, 2),
                    "short_score": round(short_score, 2),
                })

                position = None

                # ── Flip: 청산 후 반대 방향 즉시 진입 ──
                if reason == "flip":
                    new_dir = "short" if direction == "long" else "long"
                    # bearish 매크로면 long 방향으로 flip 차단
                    if new_dir == "long" and macro_bullish < 40:
                        pass  # flip 진입 없이 포지션 없는 상태로 종료
                    else:
                        size = params.position_size_pct / 100.0
                        new_allocated = capital * size
                        entry_fee = new_allocated * FEE_RATE
                        capital -= entry_fee
                        position = {
                            "direction": new_dir,
                            "entry_price": close,
                            "entry_timestamp": ts_str,
                            "allocated": new_allocated,
                            "long_score": long_score,
                            "short_score": short_score,
                        }
                        trades.append({
                            "type": "entry",
                            "direction": new_dir,
                            "timestamp": ts_str,
                            "price": close,
                            "pnl_pct": None,
                            "reason": None,
                            "long_score": round(long_score, 2),
                            "short_score": round(short_score, 2),
                        })

        # ── equity_curve 기록 ──
        if position is None:
            current_value = capital
        else:
            entry = position["entry_price"]
            dir_ = position["direction"]
            pos_allocated = position["allocated"]
            if dir_ == "long":
                unrealized_pnl = (close / entry - 1) * params.leverage
            else:  # short
                unrealized_pnl = (entry / close - 1) * params.leverage
            current_value = capital + pos_allocated * unrealized_pnl

        equity_curve.append({
            "timestamp": ts_str,
            "value": round(current_value, 4),
        })

    # MDD 계산
    peak = initial_capital
    max_drawdown = 0.0
    for point in equity_curve:
        val = point["value"]
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100 if peak > 0 else 0.0
        if dd < max_drawdown:
            max_drawdown = dd

    # 요약 통계
    sell_trades = [t for t in trades if t["type"] == "exit"]
    long_trades = [t for t in sell_trades if t["direction"] == "long"]
    short_trades = [t for t in sell_trades if t["direction"] == "short"]
    trade_count = len(sell_trades)
    winning_trades = len([t for t in sell_trades if (t["pnl_pct"] or 0) > 0])
    losing_trades = trade_count - winning_trades
    win_rate = winning_trades / trade_count if trade_count > 0 else 0.0
    total_return_pct = (capital - initial_capital) / initial_capital * 100

    return {
        "summary": {
            "total_return_pct": round(total_return_pct, 4),
            "win_rate": round(win_rate, 4),
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "long_trade_count": len(long_trades),
            "short_trade_count": len(short_trades),
            "max_drawdown_pct": round(max_drawdown, 4),
            "final_capital": round(capital, 4),
            "liquidated": liquidated,
        },
        "trades": trades,
        "equity_curve": equity_curve,
    }


# ---------------------------------------------------------------------------
# 메인 async 함수
# ---------------------------------------------------------------------------

async def run_composite_backtest(params: CompositeBacktestParams) -> dict:
    """종합 백테스트를 실행하고 결과 딕셔너리를 반환한다.

    Args:
        params: CompositeBacktestParams 인스턴스

    Returns:
        summary, trades, equity_curve, params 키를 포함한 결과 딕셔너리.
        오류 시 {"error": str} 반환 (예외 raise 금지).
    """
    # 날짜 형식 사전 검증
    for date_field in (params.start_date, params.end_date):
        if date_field:
            try:
                pd.Timestamp(date_field)
            except Exception:
                return {"error": f"날짜 형식 오류: {date_field!r} (예: '2024-01-01')"}

    loop = asyncio.get_running_loop()

    # 심볼 정규화
    ccxt_symbol = _normalize_symbol(params.symbol)

    # 1) 매크로 점수 조회
    try:
        from dashboard.backend.services.research_analyzer import _analyze_macro
        macro_result = await _analyze_macro()
        macro_level = macro_result.get("level", "neutral")
    except Exception as exc:
        logger.warning("매크로 분석 실패, neutral로 대체: %s", exc)
        macro_level = "neutral"

    macro_bullish = calc_macro_bullish_score(macro_level)

    # 2) OHLCV 데이터 수집 (스레드 풀)
    full_df = await loop.run_in_executor(None, _fetch_ohlcv, params)
    if full_df is None or full_df.empty:
        return {"error": f"OHLCV 데이터 수집 실패: symbol={ccxt_symbol}, interval={params.interval}"}

    if len(full_df) < 100:
        return {"error": f"데이터 부족: {len(full_df)}봉 (최소 100봉 필요)"}

    # 3~6) 백테스트 루프 (스레드 풀)
    result = await loop.run_in_executor(
        None, _run_backtest_sync, full_df, params, macro_bullish
    )

    if "error" in result:
        return result

    return {
        "summary": result["summary"],
        "trades": result["trades"],
        "equity_curve": result["equity_curve"],
        "params": {
            "symbol": ccxt_symbol,
            "interval": params.interval,
            "start_date": params.start_date,
            "end_date": params.end_date,
            "stop_loss_pct": params.stop_loss_pct,
            "take_profit_pct": params.take_profit_pct,
            "macro_level": macro_level,
            "macro_bullish_score": macro_bullish,
            "long_threshold": params.long_threshold,
            "short_threshold": params.short_threshold,
            "leverage": params.leverage,
            "position_size_pct": params.position_size_pct,
            "score_exit_buffer": params.score_exit_buffer,
        },
    }


# ---------------------------------------------------------------------------
# 직접 실행 테스트
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    async def _main() -> None:
        p = CompositeBacktestParams(
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01",
            end_date="2024-01-31",
            stop_loss_pct=3.0,
            take_profit_pct=5.0,
            initial_capital=10000.0,
            long_threshold=70.0,
            short_threshold=70.0,
            leverage=1.0,
            position_size_pct=100.0,
        )
        result = await run_composite_backtest(p)
        if "error" in result:
            print(f"[오류] {result['error']}")
            return

        s = result["summary"]
        print(f"총 수익률    : {s['total_return_pct']:+.2f}%")
        print(f"승률         : {s['win_rate']*100:.1f}%")
        print(f"거래 횟수    : {s['trade_count']}")
        print(f"MDD          : {s['max_drawdown_pct']:.2f}%")
        print(f"최종 자산    : {s['final_capital']:,.2f}")
        print(f"매크로 레벨  : {result['params']['macro_level']}")

    asyncio.run(_main())
