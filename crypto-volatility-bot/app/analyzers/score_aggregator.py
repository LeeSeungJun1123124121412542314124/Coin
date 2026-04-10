"""Score Aggregator — weighted final volatility score + alert level.

alert_level 체계 (백테스트 기반):
  CONFIRMED_HIGH   — 기술적 HIGH + 파생상품 확인 (OI_SURGE or SHORT_CROWDED)
                     백테스트 정밀도 92.3%
  HIGH             — 기술적 score >= 85 단독
                     백테스트 정밀도 75.0%
  LIQUIDATION_RISK — 기술적 LOW/MEDIUM + 파생상품 LIQUIDATION_RISK
                     신규 시그널
  MEDIUM           — 기술적 score 65-85 (알림 없음, 리포트에만 포함)
  LOW              — 정상 범위
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.analyzers.base import AnalysisResult

_HIGH_THRESHOLD = 85      # 백테스트 기반: 75% 정밀도
_MEDIUM_THRESHOLD = 65
_LOW_THRESHOLD = 40

# 파생상품 확인 시그널 (이 중 하나 + 기술적 HIGH = CONFIRMED_HIGH)
_DERIVATIVES_CONFIRM = {"OI_SURGE", "SHORT_CROWDED", "LIQUIDATION_RISK"}


@dataclass
class AggregatedResult:
    final_score: float      # 정기 리포트용 (온체인+기술+감성 가중합)
    alert_score: float      # 긴급 알림용 (기술적 점수)
    alert_level: str        # CONFIRMED_HIGH / HIGH / LIQUIDATION_RISK / MEDIUM / LOW
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
        derivatives: AnalysisResult | None = None,
    ) -> AggregatedResult:
        score = (
            onchain.score * self._weights["onchain"]
            + technical.score * self._weights["technical"]
            + sentiment.score * self._weights["sentiment"]
        )
        score = max(0.0, min(100.0, score))

        # alert_level 결정 (기술적 score 기준, 파생상품으로 보강)
        tech_score = technical.score
        deriv_signal = derivatives.signal if derivatives else "NEUTRAL"

        if tech_score >= _HIGH_THRESHOLD and deriv_signal in _DERIVATIVES_CONFIRM:
            alert_level = "CONFIRMED_HIGH"
        elif tech_score >= _HIGH_THRESHOLD:
            alert_level = "HIGH"
        elif deriv_signal == "LIQUIDATION_RISK" and tech_score < _HIGH_THRESHOLD:
            alert_level = "LIQUIDATION_RISK"
        elif tech_score >= _MEDIUM_THRESHOLD:
            alert_level = "MEDIUM"
        else:
            alert_level = "LOW"

        whale_alert = bool(onchain.details.get("whale_alert", False))

        details: dict[str, Any] = {
            "onchain_score": onchain.score,
            "technical_score": technical.score,
            "sentiment_score": sentiment.score,
            "onchain_signal": onchain.signal,
            "technical_signal": technical.signal,
            "sentiment_signal": sentiment.signal,
            # 메시지 포맷터 폴백 품질을 위해 핵심 detail 키를 그대로 전달
            "flow_ratio": onchain.details.get("flow_ratio"),
            "whale_volume": onchain.details.get("whale_volume"),
            "mvrv": onchain.details.get("mvrv"),
            "mvrv_signal": onchain.details.get("mvrv_signal"),
            "fear_greed_index": sentiment.details.get("fear_greed_index"),
            "base_score": technical.details.get("base_score"),
            "signal_boost": technical.details.get("signal_boost"),
        }
        if derivatives:
            details["derivatives_signal"] = deriv_signal
            details["derivatives_score"] = derivatives.score
            details["oi_3d_chg_pct"] = derivatives.details.get("oi_3d_chg_pct", 0.0)
            details["funding_rate"] = derivatives.details.get("funding_rate", 0.0)

        return AggregatedResult(
            final_score=score,
            alert_score=tech_score,
            alert_level=alert_level,
            whale_alert=whale_alert,
            details=details,
        )
