"""파생상품 분석기 — OI(미결제약정) + FR(펀딩레이트) 기반 위험도 분석.

백테스트 결과 기반 임계값:
  - OI 3일 변화 > 12%: 과열 (백테스트 상위 25% 기준)
  - FR < 0: 숏 쏠림 (반전 위험)
  - FR > 0.000082 (75th percentile): 롱 쏠림
  - OI 급등 + FR 극단 동시: 청산 캐스케이드 위험

시그널 체계:
  OI_SURGE          — OI 3일 급등 (>12%)
  SHORT_CROWDED     — FR 음수, 숏 쏠림
  LONG_CROWDED      — FR 극단 양수, 롱 쏠림
  LIQUIDATION_RISK  — OI 급등 + FR 극단 동시 (청산 위험)
  NEUTRAL           — 정상 범위
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.analyzers.base import AnalysisResult, BaseAnalyzer

# 백테스트 기반 임계값 (BTC/USDT 1년, 2025~2026)
_OI_SURGE_PCT = 12.0          # OI 3일 변화율 (%)
_FR_LONG_EXTREME = 0.000082   # FR 75th percentile (롱 쏠림)
_FR_SHORT_EXTREME = 0.0       # FR < 0 = 숏 쏠림


@dataclass
class DerivativesData:
    oi_current: float           # 현재 OI
    oi_3d_ago: float            # 3일 전 OI
    funding_rate: float         # 최근 펀딩레이트
    symbol: str = "BTC/USDT"

    @property
    def oi_3d_chg_pct(self) -> float:
        """OI 3일 변화율 (%)."""
        if self.oi_3d_ago <= 0:
            return 0.0
        return (self.oi_current - self.oi_3d_ago) / self.oi_3d_ago * 100.0


class DerivativesAnalyzer(BaseAnalyzer):
    """OI + FR 기반 파생상품 위험도 분석."""

    def analyze(self, data: DerivativesData) -> AnalysisResult:  # type: ignore[override]
        oi_chg = data.oi_3d_chg_pct
        fr = data.funding_rate

        oi_surge = abs(oi_chg) > _OI_SURGE_PCT
        fr_short = fr < _FR_SHORT_EXTREME          # 숏 쏠림
        fr_long = fr > _FR_LONG_EXTREME            # 롱 쏠림
        fr_extreme = fr_short or fr_long

        # 시그널 결정
        if oi_surge and fr_extreme:
            signal = "LIQUIDATION_RISK"
            score = 90.0
        elif oi_surge and fr_short:
            signal = "SHORT_CROWDED"
            score = 75.0
        elif oi_surge:
            signal = "OI_SURGE"
            score = 65.0
        elif fr_short:
            signal = "SHORT_CROWDED"
            score = 55.0
        elif fr_long:
            signal = "LONG_CROWDED"
            score = 50.0
        else:
            signal = "NEUTRAL"
            score = 30.0

        return AnalysisResult(
            score=score,
            signal=signal,
            details={
                "oi_current": data.oi_current,
                "oi_3d_chg_pct": round(oi_chg, 2),
                "funding_rate": data.funding_rate,
                "oi_surge": oi_surge,
                "fr_short_crowded": fr_short,
                "fr_long_crowded": fr_long,
            },
            source="derivatives",
        )
