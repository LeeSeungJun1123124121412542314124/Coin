"""매크로 시계열로부터 시점별 macro_score (0~100) 시계열을 계산한다.

설계:
  - TGA: 4주 MA 기울기 — 상승=유동성 흡수=악재(-1), 하락=공급=호재(+1)
  - M2: 전월 대비 변화율 부호 — +1 (증가, 호재) / -1 (감소, 악재)
  - BTC Dominance: 60% 기준 + 추세 — >60% & 상승=위험회피(-1, 알트 약세이지만 BTC 자체는 안정)
                   <50% = alt 시즌(+1)
  - 가중합으로 base 50에서 ±n 범위 점수 계산 후 0~100 클램프

각 신호는 해당 시점에 비해 직전 lookback 기간의 변화로 판정.
TGA는 일/주 데이터, M2는 월 데이터, Dominance는 일 데이터 — 모두 OHLCV 인덱스에 ffill로 align.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _tga_signal_series(tga: pd.Series, ma_window: int = 4) -> pd.Series:
    """TGA 4주 MA 기울기 부호.

    값: +1 (4주 MA 하락 = 유동성 공급) / 0 (변화 미미) / -1 (4주 MA 상승 = 흡수)
    """
    ma = tga.rolling(ma_window, min_periods=2).mean()
    slope = ma.diff()
    # 임계값: 값의 표준편차 5% (작은 변동 무시)
    threshold = float(slope.abs().std()) * 0.5 if len(slope) > 5 else 0.0

    def _sign(x: float) -> float:
        if pd.isna(x):
            return 0.0
        if x > threshold:
            return -1.0   # TGA 상승 = 악재
        if x < -threshold:
            return 1.0    # TGA 하락 = 호재
        return 0.0

    return slope.apply(_sign).rename("tga_signal")


def _m2_signal_series(m2: pd.Series, lookback: int = 1) -> pd.Series:
    """M2 전월(또는 lookback) 대비 변화율 부호.

    값: +1 (M2 증가 = 유동성 풀림 = 호재) / -1 (감소) / 0 (없음)
    """
    chg = m2.pct_change(lookback)
    threshold = 0.0  # M2는 보통 양수 변화 — 단순 부호로 판정

    def _sign(x: float) -> float:
        if pd.isna(x):
            return 0.0
        if x > threshold:
            return 1.0
        if x < -threshold:
            return -1.0
        return 0.0

    return chg.apply(_sign).rename("m2_signal")


def _dominance_signal_series(dom: pd.Series, ma_window: int = 8) -> pd.Series:
    """BTC Dominance 절대값 + 8주 MA 추세 결합.

    값: -1 (Dominance > 60 + 상승 추세 = 알트 자금 BTC로 회귀 = 위험회피)
        +1 (Dominance < 50 = alt 시즌 = 위험선호)
        0 (중간)
    """
    if len(dom) < 2:
        return pd.Series([0.0] * len(dom), index=dom.index, name="dominance_signal")

    ma = dom.rolling(ma_window, min_periods=2).mean()
    slope = ma.diff()

    def _sig(row_dom: float, row_slope: float) -> float:
        if pd.isna(row_dom):
            return 0.0
        if row_dom > 60.0 and (pd.notna(row_slope) and row_slope > 0):
            return -1.0
        if row_dom < 50.0:
            return 1.0
        return 0.0

    return pd.Series(
        [_sig(d, s) for d, s in zip(dom.values, slope.values)],
        index=dom.index,
        name="dominance_signal",
    )


def compute_macro_score_series(
    macro_data: dict[str, pd.Series],
    target_index: pd.DatetimeIndex,
    weight_tga: float = 1.5,
    weight_m2: float = 1.0,
    weight_dominance: float = 1.0,
    base: float = 55.0,
) -> pd.Series:
    """3개 매크로 신호를 시점별 macro_score(0~100)로 합산.

    Args:
        macro_data: {"tga": Series, "m2": Series, "dominance": Series} (없는 키는 0 신호로 처리)
        target_index: OHLCV DataFrame의 datetime 인덱스 (UTC)
        weight_*: 각 신호의 점수 가산 가중치 (-1/0/+1 신호 × weight × 10 점)
        base: 신호가 모두 0일 때의 기본 점수

    Returns:
        target_index와 동일한 길이의 macro_score Series (0~100 클램프).
        macro_data가 비어있거나 모두 비어있으면 base 값으로 채운 Series.
    """
    if not target_index.tz:
        target_index = target_index.tz_localize("UTC")

    # 각 신호를 target_index에 reindex + ffill
    def _align(signal: pd.Series) -> pd.Series:
        if signal.index.tz is None:
            signal.index = signal.index.tz_localize("UTC")
        return signal.reindex(target_index, method="ffill").fillna(0.0)

    sig_tga = _align(_tga_signal_series(macro_data["tga"])) if "tga" in macro_data else pd.Series(0.0, index=target_index)
    sig_m2 = _align(_m2_signal_series(macro_data["m2"])) if "m2" in macro_data else pd.Series(0.0, index=target_index)
    sig_dom = _align(_dominance_signal_series(macro_data["dominance"])) if "dominance" in macro_data else pd.Series(0.0, index=target_index)

    # 신호 × weight × 스케일(10점) 합산
    raw = base + 10.0 * (sig_tga * weight_tga + sig_m2 * weight_m2 + sig_dom * weight_dominance)

    # 0~100 클램프
    clamped = raw.clip(lower=0.0, upper=100.0)
    clamped.name = "macro_score"
    return clamped


def compute_macro_score_for_period(
    macro_data: dict[str, pd.Series],
    target_index: pd.DatetimeIndex,
) -> float:
    """기간 평균 macro_score 단일값 반환 (run_walk_forward 윈도우별 매크로 점수 계산용).

    target_index 기간의 macro_score 시계열 평균.
    """
    series = compute_macro_score_series(macro_data, target_index)
    return float(series.mean())
