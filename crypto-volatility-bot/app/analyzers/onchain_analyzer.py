"""Onchain Analyzer — exchange flow ratios and whale detection."""

from __future__ import annotations

from typing import Any

from app.analyzers.base import AnalysisResult, BaseAnalyzer

_FLOW_RATIO_THRESHOLD = 1.5
_WHALE_VOLUME_THRESHOLD = 50.0
_WHALE_BOOST = 15.0

# MVRV 스코어 부스트 임계값
_MVRV_EXTREME_HIGH = 3.5
_MVRV_HIGH = 2.5
_MVRV_LOW = 1.0
_MVRV_EXTREME_LOW = 0.8
_MVRV_BOOST_EXTREME = 15.0
_MVRV_BOOST_NORMAL = 10.0


class OnchainDataUnavailableError(Exception):
    """Raised when onchain data is None or critically missing."""


class OnchainAnalyzer(BaseAnalyzer):
    def analyze(self, data: Any) -> AnalysisResult:
        if data is None:
            raise OnchainDataUnavailableError("Onchain data is unavailable (None received)")

        inflow: float = float(data.get("exchange_inflow", 0))
        outflow: float = float(data.get("exchange_outflow", 0))
        whale_vol: float = float(data.get("whale_transaction_volume", 0))
        dormant: bool = bool(data.get("dormant_whale_activated", False))
        mvrv: float | None = data.get("mvrv")

        if inflow == 0 and outflow == 0:
            # 데이터 없음 — 중립 비율 사용
            ratio = 1.0
        elif outflow == 0:
            ratio = _FLOW_RATIO_THRESHOLD + 1
        else:
            ratio = inflow / outflow

        # Base score: high inflow/outflow ratio → high sell pressure
        base_score = self._normalize(ratio, 0.0, 2.5)

        # Signal
        if ratio > _FLOW_RATIO_THRESHOLD:
            signal = "HIGH_SELL_PRESSURE"
        elif outflow > 0 and inflow / outflow < (1 / _FLOW_RATIO_THRESHOLD):
            signal = "ACCUMULATION"
        else:
            signal = "NEUTRAL"

        # Whale boost
        boost = _WHALE_BOOST if whale_vol > _WHALE_VOLUME_THRESHOLD else 0.0

        # MVRV 부스트 (극단적 고평가/저평가 모두 변동성 신호)
        mvrv_boost = 0.0
        mvrv_signal = "NEUTRAL"
        if mvrv is not None:
            if mvrv > _MVRV_EXTREME_HIGH:
                mvrv_boost = _MVRV_BOOST_EXTREME
                mvrv_signal = "EXTREME_OVERVALUED"
            elif mvrv > _MVRV_HIGH:
                mvrv_boost = _MVRV_BOOST_NORMAL
                mvrv_signal = "OVERVALUED"
            elif mvrv < _MVRV_EXTREME_LOW:
                mvrv_boost = _MVRV_BOOST_EXTREME
                mvrv_signal = "EXTREME_UNDERVALUED"
            elif mvrv < _MVRV_LOW:
                mvrv_boost = _MVRV_BOOST_NORMAL
                mvrv_signal = "UNDERVALUED"

        score = self._clamp(base_score + boost + mvrv_boost)

        details: dict[str, Any] = {
            "inflow": inflow,
            "outflow": outflow,
            "flow_ratio": ratio,
            "whale_volume": whale_vol,
            "whale_alert": dormant,
            "mvrv": mvrv,
            "mvrv_signal": mvrv_signal,
        }

        return AnalysisResult(score=score, signal=signal, details=details, source="onchain")
