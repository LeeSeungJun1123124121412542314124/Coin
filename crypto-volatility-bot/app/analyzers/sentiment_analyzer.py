"""Sentiment Analyzer — Fear & Greed Index based volatility scoring."""

from __future__ import annotations

from typing import Any

from app.analyzers.base import AnalysisResult, BaseAnalyzer

_EXTREME_FEAR_THRESHOLD = 25
_EXTREME_GREED_THRESHOLD = 75


class SentimentAnalyzer(BaseAnalyzer):
    def analyze(self, data: Any) -> AnalysisResult:
        if data is None:
            return AnalysisResult(score=50.0, signal="NEUTRAL", details={}, source="sentiment")

        fg: int = int(data.get("fear_greed_index", 50))

        # Boost formula: abs(50 - fg) * 0.5  (only outside 25-75 range)
        if fg < _EXTREME_FEAR_THRESHOLD or fg > _EXTREME_GREED_THRESHOLD:
            volatility_boost = abs(50 - fg) * 0.5
        else:
            volatility_boost = 0.0

        # Base score: always start at 50, extremes push it higher
        score = self._clamp(50.0 + volatility_boost)

        if fg < _EXTREME_FEAR_THRESHOLD:
            signal = "EXTREME_FEAR"
        elif fg > _EXTREME_GREED_THRESHOLD:
            signal = "EXTREME_GREED"
        else:
            signal = "NEUTRAL"

        details = {"fear_greed_index": fg, "volatility_boost": volatility_boost}
        return AnalysisResult(score=score, signal=signal, details=details, source="sentiment")
