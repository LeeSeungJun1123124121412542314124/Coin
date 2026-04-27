"""현재 신호 분석기 — 최근 200봉 기준 각 TA 지표의 현재 신호 상태 반환."""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.ta_indicators import (
    signals_adx,
    signals_atr,
    signals_bollinger,
    signals_ema,
    signals_fibonacci,
    signals_ichimoku,
    signals_ma,
    signals_macd,
    signals_rsi,
    signals_stochastic,
    signals_support_resistance,
    signals_trendline,
    signals_volume,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OHLCV 로드
# ---------------------------------------------------------------------------

def _load_ohlcv(symbol: str, lookback: int = 200) -> dict | None:
    """coin_ohlcv_1h에서 OHLCV 데이터 로드."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, open, high, low, close, volume "
            "FROM coin_ohlcv_1h "
            "WHERE symbol=? "
            "ORDER BY timestamp DESC LIMIT ?",
            (symbol, lookback),
        ).fetchall()
    if not rows or len(rows) < 80:
        return None
    rows = list(reversed(rows))
    return {
        "closes":  np.array([r[4] for r in rows], dtype=np.float64),
        "highs":   np.array([r[2] for r in rows], dtype=np.float64),
        "lows":    np.array([r[3] for r in rows], dtype=np.float64),
        "volumes": np.array([r[5] for r in rows], dtype=np.float64),
    }


# ---------------------------------------------------------------------------
# 현재 신호 추출
# ---------------------------------------------------------------------------

def _get_current_signal(signals: list[tuple[int, str]], total_bars: int) -> str:
    """최근 20봉 이내 마지막 신호만 현재 신호로 인정. 없으면 neutral."""
    if not signals:
        return "neutral"
    last_idx, last_dir = signals[-1]
    if total_bars - last_idx > 20:
        return "neutral"
    return last_dir


# ---------------------------------------------------------------------------
# 지표별 설명 문자열
# ---------------------------------------------------------------------------

_DESC = {
    "RSI": {
        "long": "과매도(RSI<30)",
        "neutral": "중립",
        "short": "과매도 탈출/과매수",
    },
    "MACD": {
        "long": "골든크로스",
        "neutral": "중립",
        "short": "데드크로스",
    },
    "BB": {
        "long": "하단 재진입",
        "neutral": "중립",
        "short": "상단 재진입",
    },
    "MA": {
        "long": "MA 상향돌파",
        "neutral": "중립",
        "short": "MA 하향돌파",
    },
    "EMA": {
        "long": "EMA 상향돌파",
        "neutral": "중립",
        "short": "EMA 하향돌파",
    },
    "볼륨": {
        "long": "거래량 급등+상승",
        "neutral": "중립",
        "short": "거래량 급등+하락",
    },
    "지지/저항": {
        "long": "지지선 반등",
        "neutral": "중립",
        "short": "저항선 거절",
    },
    "피보나치": {
        "long": "61.8% 지지",
        "neutral": "중립",
        "short": "61.8% 저항",
    },
    "일목균형표": {
        "long": "구름 위+골든",
        "neutral": "중립",
        "short": "구름 아래+데드",
    },
    "스토캐스틱": {
        "long": "과매도 크로스업",
        "neutral": "중립",
        "short": "과매수 크로스다운",
    },
    "트렌드라인": {
        "long": "상승 추세",
        "neutral": "중립",
        "short": "하락 추세",
    },
    "ADX": {
        "long": "+DI 상향돌파",
        "neutral": "중립",
        "short": "-DI 상향돌파",
    },
    "ATR": {
        "long": "변동성 급등+상승",
        "neutral": "중립",
        "short": "변동성 급등+하락",
    },
}


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------

async def get_current_signals(symbol: str) -> dict | None:
    """
    최근 200봉 기준 13개 TA 지표의 현재 신호 상태를 반환한다.

    Returns:
    {
      "symbol": "BTCUSDT",
      "indicators": [
        {"name": "RSI", "signal": "long"|"short"|"neutral", "value": <last RSI value or None>, "desc": "설명"},
        ...
      ],
      "score": 64,          # -100 to +100
      "bias": "long",       # "long" | "short" | "neutral"
      "confidence": 0.72    # 0.0 to 1.0
    }
    Returns None if insufficient data.
    """
    ohlcv = await asyncio.to_thread(_load_ohlcv, symbol)
    if ohlcv is None:
        return None

    closes  = ohlcv["closes"]
    highs   = ohlcv["highs"]
    lows    = ohlcv["lows"]
    volumes = ohlcv["volumes"]

    # 각 지표별 신호 계산
    def _run_indicators() -> list[dict]:
        results = []
        total_bars = len(closes)

        # 1. RSI
        try:
            sig = _get_current_signal(signals_rsi(closes), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: RSI")
            sig = "neutral"
        results.append({"name": "RSI", "signal": sig, "value": None, "desc": _DESC.get("RSI", {}).get(sig, "")})

        # 2. MACD
        try:
            sig = _get_current_signal(signals_macd(closes), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: MACD")
            sig = "neutral"
        results.append({"name": "MACD", "signal": sig, "value": None, "desc": _DESC.get("MACD", {}).get(sig, "")})

        # 3. BB (볼린저밴드)
        try:
            sig = _get_current_signal(signals_bollinger(closes), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: BB")
            sig = "neutral"
        results.append({"name": "BB", "signal": sig, "value": None, "desc": _DESC.get("BB", {}).get(sig, "")})

        # 4. MA
        try:
            sig = _get_current_signal(signals_ma(closes), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: MA")
            sig = "neutral"
        results.append({"name": "MA", "signal": sig, "value": None, "desc": _DESC.get("MA", {}).get(sig, "")})

        # 5. EMA
        try:
            sig = _get_current_signal(signals_ema(closes), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: EMA")
            sig = "neutral"
        results.append({"name": "EMA", "signal": sig, "value": None, "desc": _DESC.get("EMA", {}).get(sig, "")})

        # 6. 볼륨
        try:
            sig = _get_current_signal(signals_volume(closes, volumes), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: 볼륨")
            sig = "neutral"
        results.append({"name": "볼륨", "signal": sig, "value": None, "desc": _DESC.get("볼륨", {}).get(sig, "")})

        # 7. 지지/저항
        try:
            sig = _get_current_signal(signals_support_resistance(closes, highs, lows), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: 지지/저항")
            sig = "neutral"
        results.append({"name": "지지/저항", "signal": sig, "value": None, "desc": _DESC.get("지지/저항", {}).get(sig, "")})

        # 8. 피보나치
        try:
            sig = _get_current_signal(signals_fibonacci(closes, highs, lows), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: 피보나치")
            sig = "neutral"
        results.append({"name": "피보나치", "signal": sig, "value": None, "desc": _DESC.get("피보나치", {}).get(sig, "")})

        # 9. 일목균형표
        try:
            sig = _get_current_signal(signals_ichimoku(closes, highs, lows), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: 일목균형표")
            sig = "neutral"
        results.append({"name": "일목균형표", "signal": sig, "value": None, "desc": _DESC.get("일목균형표", {}).get(sig, "")})

        # 10. 스토캐스틱
        try:
            sig = _get_current_signal(signals_stochastic(closes, highs, lows), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: 스토캐스틱")
            sig = "neutral"
        results.append({"name": "스토캐스틱", "signal": sig, "value": None, "desc": _DESC.get("스토캐스틱", {}).get(sig, "")})

        # 11. 트렌드라인 — 매봉 선형회귀 계산이므로 최신 신호 = 현재 상태. 20봉 컷오프 미적용.
        try:
            tl_signals = signals_trendline(closes)
            sig = tl_signals[-1][1] if tl_signals else "neutral"
        except Exception:
            logger.exception("지표 계산 실패: 트렌드라인")
            sig = "neutral"
        results.append({"name": "트렌드라인", "signal": sig, "value": None, "desc": _DESC.get("트렌드라인", {}).get(sig, "")})

        # 12. ADX
        try:
            sig = _get_current_signal(signals_adx(closes, highs, lows), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: ADX")
            sig = "neutral"
        results.append({"name": "ADX", "signal": sig, "value": None, "desc": _DESC.get("ADX", {}).get(sig, "")})

        # 13. ATR
        try:
            sig = _get_current_signal(signals_atr(closes, highs, lows), total_bars)
        except Exception:
            logger.exception("지표 계산 실패: ATR")
            sig = "neutral"
        results.append({"name": "ATR", "signal": sig, "value": None, "desc": _DESC.get("ATR", {}).get(sig, "")})

        return results

    indicators = await asyncio.to_thread(_run_indicators)

    # 점수 계산
    votes = []
    for ind in indicators:
        if ind["signal"] == "long":
            votes.append(1)
        elif ind["signal"] == "short":
            votes.append(-1)
        else:
            votes.append(0)

    score = round(sum(votes) / len(indicators) * 100)

    # bias 결정
    if abs(score) < 20:
        bias = "neutral"
    elif score >= 20:
        bias = "long"
    else:
        bias = "short"

    # confidence
    confidence = round(abs(score) / 100, 2)

    return {
        "symbol": symbol,
        "indicators": indicators,
        "score": score,
        "bias": bias,
        "confidence": confidence,
    }
