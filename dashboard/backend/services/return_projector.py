"""수익 예측 서비스 — 신호 스코어 × ATR 변동성 × 시간 배수로 예상 수익 범위 계산."""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.signal_analyzer import get_current_signals
from dashboard.backend.services.ta_indicators import _atr

logger = logging.getLogger(__name__)

# 기간별 시간 배수
_TIME_MULTIPLIERS: dict[str, float] = {
    "1d": 1.0,
    "1w": 2.5,
    "1m": 5.0,
    "3m": 10.0,
}

# 기간별 신뢰도 감쇠 계수
_CONFIDENCE_DECAY: dict[str, float] = {
    "1d": 1.0,
    "1w": 0.85,
    "1m": 0.70,
    "3m": 0.58,
}


def _load_ohlcv(symbol: str, lookback: int = 200) -> dict | None:
    """DB에서 최근 1h OHLCV 데이터를 로드한다."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, open, high, low, close, volume "
            "FROM coin_ohlcv_1h "
            "WHERE symbol=? "
            "ORDER BY timestamp DESC LIMIT ?",
            (symbol, lookback),
        ).fetchall()
    if not rows or len(rows) < 30:
        return None
    rows = list(reversed(rows))
    return {
        "closes": np.array([r[4] for r in rows], dtype=np.float64),
        "highs":  np.array([r[2] for r in rows], dtype=np.float64),
        "lows":   np.array([r[3] for r in rows], dtype=np.float64),
    }


async def get_projection(symbol: str, direction: str, leverage: int = 1) -> dict | None:
    """
    신호 스코어 × ATR 변동성 × 시간 배수로 기간별 예상 수익 범위를 계산한다.

    Args:
        symbol: 심볼 (예: "BTCUSDT")
        direction: "long" | "short"
        leverage: 1~64

    Returns:
        {
          "symbol": "BTCUSDT",
          "direction": "long",
          "leverage": 5,
          "signal_score": 64,
          "atr_pct": 2.1,
          "horizons": [
            {"period": "1d", "base_pct": 1.2, "best_pct": 3.8, "worst_pct": -0.9, "confidence": 0.68},
            {"period": "1w", "base_pct": 3.0, "best_pct": 9.5, "worst_pct": -2.25, "confidence": 0.68},
            {"period": "1m", "base_pct": 6.0, "best_pct": 19.0, "worst_pct": -4.5, "confidence": 0.56},
            {"period": "3m", "base_pct": 12.0, "best_pct": 38.0, "worst_pct": -9.0, "confidence": 0.46}
          ]
        }
        OHLCV 데이터가 부족하면 None 반환.
    """
    # OHLCV 로드 (블로킹 DB 작업은 스레드에서 실행)
    ohlcv = await asyncio.to_thread(_load_ohlcv, symbol)
    if ohlcv is None:
        return None

    closes = ohlcv["closes"]
    highs  = ohlcv["highs"]
    lows   = ohlcv["lows"]

    # ATR(14) 계산
    atr_arr = _atr(highs, lows, closes, 14)
    current_atr = atr_arr[-1]
    current_price = closes[-1]

    if np.isnan(current_atr) or current_price == 0:
        return None

    atr_pct = round(current_atr / current_price * 100, 2)

    # 신호 스코어 조회
    signals_data = await get_current_signals(symbol)
    signal_score: float = signals_data["score"] if signals_data else 0

    # 방향 조정: short은 점수를 반전 (가격 하락 시 이익)
    effective_score = signal_score if direction == "long" else -signal_score

    # TA 신뢰도 기본값 (범위: 0.0 ~ 0.8)
    confidence_base = abs(signal_score) / 100 * 0.8

    # 기간별 예측 계산
    horizons = []
    for period, time_multiplier in _TIME_MULTIPLIERS.items():
        # 레버리지 적용 기대 수익률
        base_pct = effective_score / 100 * atr_pct * time_multiplier
        base_pct_leveraged = base_pct * leverage
        best_pct  = base_pct_leveraged * 1.5
        worst_pct = base_pct_leveraged * -0.5  # 반대 방향 꼬리 리스크

        # 시간 경과에 따른 신뢰도 감쇠
        confidence = round(confidence_base * _CONFIDENCE_DECAY[period], 2)
        confidence = min(confidence, 1.0)

        horizons.append({
            "period":    period,
            "base_pct":  round(base_pct_leveraged, 2),
            "best_pct":  round(best_pct, 2),
            "worst_pct": round(worst_pct, 2),
            "confidence": confidence,
        })

    return {
        "symbol":       symbol,
        "direction":    direction,
        "leverage":     leverage,
        "signal_score": signal_score,
        "atr_pct":      atr_pct,
        "horizons":     horizons,
    }
