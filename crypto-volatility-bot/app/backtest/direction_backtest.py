"""1차 기술 방향 백테스트 — 슬라이딩 윈도우로 방향 적중률 측정.

엔진(engine.py)은 변동성 점수용. 본 모듈은 방향 모델의 기술 1차 방향만
과거 OHLCV로 평가한다(보조 신뢰도 입력은 과거 데이터 부재로 None).
"""

from __future__ import annotations

import logging

import pandas as pd

from app.analyzers.direction_model import compute_direction
from app.analyzers.technical_analyzer import TechnicalAnalyzer

logger = logging.getLogger(__name__)


def run_direction_backtest(
    df: pd.DataFrame,
    *,
    window_size: int = 100,
    evaluation_bars: int = 24,
    config_path: str | None = None,
) -> dict[str, float]:
    """방향 적중률 측정.

    Args:
        df: 전체 과거 OHLCV.
        window_size: 분석 윈도우 봉 수.
        evaluation_bars: 방향 평가 호라이즌(1h봉 기준 24=24h).

    Returns:
        {"hit_rate", "total_evaluated", "correct"} — final_direction이 neutral인
        구간은 평가 제외.
    """
    analyzer = TechnicalAnalyzer(config_path)
    n = len(df)
    correct = 0
    total = 0

    for end in range(window_size, n - evaluation_bars):
        window = df.iloc[end - window_size : end].reset_index(drop=True)
        try:
            res = analyzer.analyze(window)
        except Exception as e:  # noqa: BLE001
            logger.debug("윈도우 %d 분석 실패 (건너뜀): %s", end, e)
            continue

        d = res.details
        bias = compute_direction(
            ha_bullish=d.get("ha_direction") == "bullish",
            ha_bearish=d.get("ha_direction") == "bearish",
            hma_cross=d.get("hma_cross"),
            macd_cross=d.get("macd_cross"),
            funding_rate=None, flow_ratio=None, mvrv=None, fear_greed=None,
        )
        if bias.final_direction == "neutral":
            continue

        future_close = float(df.iloc[end + evaluation_bars - 1]["close"])
        current_close = float(df.iloc[end - 1]["close"])
        actual = "long" if future_close > current_close else "short"
        if actual == bias.final_direction:
            correct += 1
        total += 1

    return {
        "hit_rate": correct / total if total > 0 else 0.0,
        "total_evaluated": float(total),
        "correct": float(correct),
    }
