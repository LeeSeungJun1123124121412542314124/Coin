"""Message formatter — 5가지 알림 유형.

알림 체계 (정밀도 우선):
  confirmed_high_alert  — score>=85 + 파생상품 확인 (92% 신뢰도)
  high_alert            — score>=85 단독 (75% 신뢰도)
  liquidation_risk_alert — 기술LOW + OI/FR 극단 (신규)
  whale_alert           — 온체인 고래 감지
  periodic_report       — 12h 정기 리포트 (파생상품 포함)
  daily_summary         — 일간 통계
"""

from __future__ import annotations

from typing import Any

from app.analyzers.score_aggregator import AggregatedResult

_RECOMMENDATIONS = {
    "CONFIRMED_HIGH": "파생상품 확인 시그널. 포지션 즉시 점검 권고.",
    "HIGH": "기술적 변동성 경보. 파생상품 미확인 — 참고용 알림.",
    "LIQUIDATION_RISK": "OI+FR 극단 동시 발생. 청산 캐스케이드 주의.",
    "MEDIUM": "보통 변동성. 시장 모니터링 유지.",
    "LOW": "안정적인 시장 상황.",
    "EMERGENCY": "긴급 구간입니다. 포지션 노출도를 즉시 축소하세요.",
}

_SIGNAL_EMOJI = {
    "HIGH_SELL_PRESSURE": "🔴",
    "ACCUMULATION": "🟢",
    "NEUTRAL": "⚪",
    "EXTREME_FEAR": "😱",
    "EXTREME_GREED": "🤑",
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "🟢",
    "OI_SURGE": "📈",
    "SHORT_CROWDED": "⚡",
    "LONG_CROWDED": "🔥",
    "LIQUIDATION_RISK": "💥",
}


def _fr_pct(fr: float) -> str:
    """펀딩레이트를 퍼센트 문자열로 변환."""
    return f"{fr * 100:.4f}%"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_booster_top3(raw: Any) -> str:
    if not isinstance(raw, dict) or not raw:
        return "없음"
    pairs: list[tuple[str, float]] = []
    for name, boost in raw.items():
        pairs.append((str(name), _to_float(boost, 0.0)))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return ", ".join(f"{name}(+{boost:.1f})" for name, boost in pairs[:3])


def _recommendation(level: str) -> str:
    return _RECOMMENDATIONS.get(level, "변동성 변화 구간입니다. 리스크 관리 비중을 유지하세요.")


class MessageFormatter:
    def confirmed_high_alert(self, symbol: str, result: AggregatedResult) -> str:
        """92% 신뢰도 — 기술적 HIGH + 파생상품 확인."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        oi_chg = _to_float(d.get("oi_3d_chg_pct"), 0.0)
        fr = _to_float(d.get("funding_rate"), 0.0)
        deriv_sig = str(d.get("derivatives_signal", "NEUTRAL"))
        tech_sig = str(d.get("technical_signal", "N/A"))
        tech_score = _to_float(d.get("technical_score"), 0.0)

        lines = [
            "🚨 <b>변동성 확인 경보</b>",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            "<b>한줄 요약</b>",
            f"{result.alert_level} | 종합 {result.final_score:.1f}/100 | 기술 {tech_score:.1f} | 파생 {deriv_sig}",
            "",
            "<b>발생 근거</b>",
            f"- 기술: {tech_score:.1f}점 ({tech_sig})",
            f"- 파생: OI 3일 {oi_chg:+.1f}% | FR {_fr_pct(fr)} | 시그널 {deriv_sig}",
            "",
            "<b>신뢰도</b>",
            "파생상품 이중 확인 완료 — 신뢰도 약 92%",
            "",
            f"💡 {_recommendation('CONFIRMED_HIGH')}",
        ]
        return "\n".join(lines)

    def high_alert(self, symbol: str, result: AggregatedResult) -> str:
        """75% 신뢰도 — 기술적 HIGH 단독."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        tech_sig = str(d.get("technical_signal", "N/A"))
        deriv_sig = str(d.get("derivatives_signal", "NEUTRAL"))
        tech_score = _to_float(d.get("technical_score"), 0.0)
        oi_chg = _to_float(d.get("oi_3d_chg_pct"), 0.0)
        fr = _to_float(d.get("funding_rate"), 0.0)

        lines = [
            "📊 <b>변동성 경보</b>",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            "<b>한줄 요약</b>",
            f"{result.alert_level} | 종합 {result.final_score:.1f}/100 | 기술 {tech_score:.1f} | 파생 {deriv_sig}",
            "",
            "<b>발생 근거</b>",
            f"- 기술: {tech_score:.1f}점 ({tech_sig})",
            f"- 파생: OI 3일 {oi_chg:+.1f}% | FR {_fr_pct(fr)} | 시그널 {deriv_sig}",
            "",
            "<b>신뢰도</b>",
            "기술적 변동성 경보 — 신뢰도 약 75%",
            "",
            f"💡 {_recommendation('HIGH')}",
        ]
        return "\n".join(lines)

    def liquidation_risk_alert(self, symbol: str, result: AggregatedResult) -> str:
        """신규 — 기술적 LOW이지만 OI+FR 극단 동시."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        oi_chg = _to_float(d.get("oi_3d_chg_pct"), 0.0)
        fr = _to_float(d.get("funding_rate"), 0.0)
        tech_score = _to_float(d.get("technical_score"), 0.0)
        tech_sig = str(d.get("technical_signal", "N/A"))
        deriv_sig = str(d.get("derivatives_signal", "LIQUIDATION_RISK"))

        lines = [
            "⚡ <b>청산 위험 경보</b>",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            "<b>발생 근거</b>",
            f"- 기술: {tech_score:.1f}점 ({tech_sig})",
            f"- 파생: OI 3일 {oi_chg:+.1f}% | FR {_fr_pct(fr)} | 시그널 {deriv_sig}",
            "",
            "기술 점수 대비 파생상품 과열 신호가 강합니다.",
            f"💡 {_recommendation('LIQUIDATION_RISK')}",
        ]
        return "\n".join(lines)

    def whale_alert(self, symbol: str, result: AggregatedResult) -> str:
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        onchain_score = _to_float(d.get("onchain_score"), 0.0)
        onchain_sig = str(d.get("onchain_signal", "N/A"))
        flow_ratio = _to_float(d.get("flow_ratio"), 0.0)
        whale_volume = _to_float(d.get("whale_volume"), 0.0)
        whale_flag = "감지" if result.whale_alert else "미감지"
        lines = [
            "🐋 <b>고래 활동 감지</b>",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            "<b>핵심 지표</b>",
            f"- 온체인: {onchain_score:.1f} ({onchain_sig})",
            f"- 유입/유출 비율: {flow_ratio:.2f}",
            f"- 고래 거래량: {whale_volume:.1f} | 휴면 고래: {whale_flag}",
            "",
            "💡 단기 변동성 확대 가능성. 포지션 크기 점검 권장.",
        ]
        return "\n".join(lines)

    def periodic_report(self, symbol: str, result: AggregatedResult) -> str:
        """12h 정기 리포트 — 파생상품/감성 포함."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        tech_score = _to_float(d.get("technical_score"), 0.0)
        onchain_score = _to_float(d.get("onchain_score"), 0.0)
        sentiment_score = _to_float(d.get("sentiment_score"), 0.0)
        tech_sig = str(d.get("technical_signal", "N/A"))
        onchain_sig = str(d.get("onchain_signal", "N/A"))
        sentiment_sig = str(d.get("sentiment_signal", "N/A"))
        deriv_sig = str(d.get("derivatives_signal", "N/A"))
        oi_chg = _to_float(d.get("oi_3d_chg_pct"), 0.0)
        fr = _to_float(d.get("funding_rate"), 0.0)
        flow_ratio = _to_float(d.get("flow_ratio"), 0.0)
        fgi = int(_to_float(d.get("fear_greed_index"), 0.0)) if d.get("fear_greed_index") is not None else None
        base_score = d.get("base_score")
        boost_obj = d.get("signal_boost")
        boost_total = None
        booster_top3 = "없음"
        if isinstance(boost_obj, dict):
            boost_total = _to_float(boost_obj.get("total_boost"), 0.0)
            booster_top3 = _format_booster_top3(boost_obj.get("active_boosters"))

        lines = [
            f"📊 <b>변동성 정기 리포트</b> — {symbol}",
            f"🕐 {ts}",
            "",
            "<b>한줄 요약</b>",
            f"{result.alert_level} | 종합 {result.final_score:.1f}/100 | 기술 {tech_score:.1f} | 파생 {deriv_sig}",
            "",
            "<b>핵심 지표</b>",
            f"- 온체인: {onchain_sig} (점수 {onchain_score:.1f}, 유입/유출 비율 {flow_ratio:.2f})",
            f"- 감성: {sentiment_sig} (점수 {sentiment_score:.1f}" + (f", 공포탐욕지수 {fgi})" if fgi is not None else ")"),
            f"- 파생: OI 3일 {oi_chg:+.1f}% | FR {_fr_pct(fr)} | 시그널 {deriv_sig}",
            "",
            "<b>트리거 근거</b>",
        ]

        if base_score is not None and boost_total is not None:
            lines.append(f"- 기술 점수 = 기본 {_to_float(base_score):.1f} + 부스터 {boost_total:.1f}")
        else:
            lines.append("- 기술 점수 분해 데이터 없음")
        lines.append(f"- 활성 부스터: {booster_top3}")

        lines += ["", f"💡 {_recommendation(result.alert_level)}"]
        return "\n".join(lines)

    def daily_summary(self, symbol: str, stats: dict[str, Any]) -> str:
        lines = [
            f"📅 <b>일간 변동성 요약</b> — {symbol}",
            f"날짜: {stats.get('date', 'N/A')}",
            "",
            f"  최고 점수: {stats.get('high', 0):.1f}",
            f"  최저 점수: {stats.get('low', 0):.1f}",
            f"  평균 점수: {stats.get('avg', 0):.1f}",
        ]
        return "\n".join(lines)
