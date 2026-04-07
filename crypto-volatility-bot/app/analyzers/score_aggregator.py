"""Score Aggregator — weighted final volatility score + alert level."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.analyzers.base import AnalysisResult

_EMERGENCY_THRESHOLD = 80
_HIGH_THRESHOLD = 60
_MEDIUM_THRESHOLD = 40


@dataclass
class AggregatedResult:
    final_score: float   # 정기 리포트용 (온체인 + 기술적 + 감성 가중합)
    alert_score: float   # 긴급 알림용 (기술적 점수 100%)
    alert_level: str
    whale_alert: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)


class ScoreAggregator:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or {"onchain": 0.40, "technical": 0.35, "sentiment": 0.25}

    def aggregate(
        self,
        onchain: AnalysisResult,
        technical: AnalysisResult,
        sentiment: AnalysisResult,
    ) -> AggregatedResult:
        score = (
            onchain.score * self._weights["onchain"]
            + technical.score * self._weights["technical"]
            + sentiment.score * self._weights["sentiment"]
        )
        score = max(0.0, min(100.0, score))

        if score >= _EMERGENCY_THRESHOLD:
            alert_level = "EMERGENCY"
        elif score >= _HIGH_THRESHOLD:
            alert_level = "HIGH"
        elif score >= _MEDIUM_THRESHOLD:
            alert_level = "MEDIUM"
        else:
            alert_level = "LOW"

        whale_alert = bool(onchain.details.get("whale_alert", False))

        return AggregatedResult(
            final_score=score,
            alert_score=technical.score,
            alert_level=alert_level,
            whale_alert=whale_alert,
            details={
                "onchain_score": onchain.score,
                "technical_score": technical.score,
                "sentiment_score": sentiment.score,
                "onchain_signal": onchain.signal,
                "technical_signal": technical.signal,
                "sentiment_signal": sentiment.signal,
            },
        )
