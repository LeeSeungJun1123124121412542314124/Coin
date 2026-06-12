"""방향 모델 — 계층 게이트(기술 1차) + 보조 신뢰도 가감.

기술(HA + HMA/MACD 크로스)이 1차 방향(long/short/neutral)을 결정한다.
파생·온체인은 confirm/divergence로 신뢰도를 ±15 가감, MVRV·F&G 극단은
±10 nudge. 신뢰도<30이면 방향을 '중립'으로 강등한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analyzers import direction_constants as C


@dataclass
class DirectionBias:
    primary_direction: str   # "long" | "short" | "neutral" (기술 1차)
    confidence: float        # 0~100
    final_direction: str     # "long" | "short" | "neutral" (컷오프 반영)
    confirm_count: int       # 1차 방향을 confirm한 보조 카테고리 수
    divergence_count: int    # 1차 방향에 divergence인 보조 카테고리 수
    evidence: str            # 근거 한 줄 ("파생 confirm · 온체인 divergence")


_OPPOSING_CROSS = {"long": "death", "short": "golden"}


def _primary_from_technical(
    ha_bullish: bool, ha_bearish: bool, hma_cross: str | None, macd_cross: str | None
) -> str:
    """HA 1차 방향 + 크로스 둘 다 반대면 중립 강등."""
    if ha_bullish:
        primary = "long"
    elif ha_bearish:
        primary = "short"
    else:
        return "neutral"

    opp = _OPPOSING_CROSS[primary]
    hma_opp = hma_cross == opp
    macd_opp = macd_cross == opp
    if hma_opp and macd_opp:
        return "neutral"
    return primary


def _fr_lean(funding_rate: float | None) -> str | None:
    """파생 컨트레리언 레인: FR<0 숏쏠림→롱, FR>0 롱쏠림→숏."""
    if funding_rate is None or abs(funding_rate) < C.FR_DEADBAND:
        return None
    return "long" if funding_rate < 0 else "short"


def _flow_lean(flow_ratio: float | None) -> str | None:
    """온체인 레인: flow_ratio<1 매집→롱, >1 유입우위→숏."""
    if flow_ratio is None or C.FLOW_RATIO_LOW <= flow_ratio <= C.FLOW_RATIO_HIGH:
        return None
    return "long" if flow_ratio < 1.0 else "short"


def _mvrv_lean(mvrv: float | None) -> str | None:
    """MVRV 극단만: >3.5 숏, <0.8 롱."""
    if mvrv is None:
        return None
    if mvrv > C.MVRV_OVERHEATED:
        return "short"
    if mvrv < C.MVRV_UNDERVALUED:
        return "long"
    return None


def _fg_lean(fear_greed: float | None) -> str | None:
    """F&G 극단만: <25 롱, >75 숏."""
    if fear_greed is None:
        return None
    if fear_greed < C.FG_EXTREME_FEAR:
        return "long"
    if fear_greed > C.FG_EXTREME_GREED:
        return "short"
    return None


def compute_direction(
    *,
    ha_bullish: bool,
    ha_bearish: bool,
    hma_cross: str | None,
    macd_cross: str | None,
    funding_rate: float | None,
    flow_ratio: float | None,
    mvrv: float | None,
    fear_greed: float | None,
) -> DirectionBias:
    primary = _primary_from_technical(ha_bullish, ha_bearish, hma_cross, macd_cross)

    if primary == "neutral":
        return DirectionBias(
            primary_direction="neutral",
            confidence=C.BASE_CONFIDENCE,
            final_direction="neutral",
            confirm_count=0,
            divergence_count=0,
            evidence="방향 불명확",
        )

    confidence = C.BASE_CONFIDENCE
    confirm_count = 0
    divergence_count = 0
    parts: list[str] = []

    # 보조 카테고리(파생/온체인) — confirm/divergence ±15
    for label, lean in (("파생", _fr_lean(funding_rate)), ("온체인", _flow_lean(flow_ratio))):
        if lean is None:
            continue
        if lean == primary:
            confidence += C.CONFIRM_DELTA
            confirm_count += 1
            parts.append(f"{label} confirm")
        else:
            confidence += C.DIVERGENCE_DELTA
            divergence_count += 1
            parts.append(f"{label} divergence")

    # nudge(MVRV/F&G) — ±10, confirm/divergence 카운트엔 미포함
    for label, lean in (("MVRV", _mvrv_lean(mvrv)), ("F&G", _fg_lean(fear_greed))):
        if lean is None:
            continue
        confidence += C.NUDGE_DELTA if lean == primary else -C.NUDGE_DELTA
        parts.append(f"{label} nudge")

    confidence = max(C.CONFIDENCE_MIN, min(C.CONFIDENCE_MAX, confidence))
    final = primary if confidence >= C.CONFIDENCE_CUTOFF else "neutral"
    evidence = " · ".join(parts) if parts else "보조 신호 없음"

    return DirectionBias(
        primary_direction=primary,
        confidence=confidence,
        final_direction=final,
        confirm_count=confirm_count,
        divergence_count=divergence_count,
        evidence=evidence,
    )
