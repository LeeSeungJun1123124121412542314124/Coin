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


class MessageFormatter:
    def confirmed_high_alert(self, symbol: str, result: AggregatedResult) -> str:
        """92% 신뢰도 — 기술적 HIGH + 파생상품 확인."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        oi_chg = d.get("oi_3d_chg_pct", 0.0)
        fr = d.get("funding_rate", 0.0)
        deriv_sig = d.get("derivatives_signal", "N/A")
        tech_sig = d.get("technical_signal", "")

        lines = [
            "🚨 <b>HIGH 변동성 확인</b> 🚨",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            f"<b>종합 점수</b>: {result.final_score:.1f} | <b>기술적</b>: {d.get('technical_score', 0):.1f}",
            "",
            "<b>[기술적 분석]</b>",
            f"  시그널: {tech_sig}",
            "",
            "<b>[파생상품 확인]</b>",
            f"  OI 3일 변화: {oi_chg:+.1f}%",
            f"  펀딩레이트: {_fr_pct(fr)} ({deriv_sig})",
            "",
            f"✅ <b>파생상품 이중 확인 완료</b> — 신뢰도 ~92%",
            f"💡 {_RECOMMENDATIONS['CONFIRMED_HIGH']}",
        ]
        return "\n".join(lines)

    def high_alert(self, symbol: str, result: AggregatedResult) -> str:
        """75% 신뢰도 — 기술적 HIGH 단독."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        tech_sig = d.get("technical_signal", "")
        deriv_sig = d.get("derivatives_signal", "N/A")

        lines = [
            "📊 <b>변동성 경보</b>",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            f"<b>기술적 점수</b>: {d.get('technical_score', 0):.1f} | 시그널: {tech_sig}",
            f"<b>파생상품</b>: {deriv_sig} (미확인)",
            "",
            f"⚠️ 신뢰도 ~75% — 파생상품 미확인 참고용",
            f"💡 {_RECOMMENDATIONS['HIGH']}",
        ]
        return "\n".join(lines)

    def liquidation_risk_alert(self, symbol: str, result: AggregatedResult) -> str:
        """신규 — 기술적 LOW이지만 OI+FR 극단 동시."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        oi_chg = d.get("oi_3d_chg_pct", 0.0)
        fr = d.get("funding_rate", 0.0)

        lines = [
            "⚡ <b>청산 위험 경보</b>",
            f"심볼: {symbol} | 시간: {ts}",
            "",
            f"<b>OI 3일 변화</b>: {oi_chg:+.1f}% (과열)",
            f"<b>펀딩레이트</b>: {_fr_pct(fr)}",
            "",
            "기술적 변동성은 낮지만 파생상품 극단값 동시 발생.",
            f"💡 {_RECOMMENDATIONS['LIQUIDATION_RISK']}",
        ]
        return "\n".join(lines)

    def whale_alert(self, symbol: str, result: AggregatedResult) -> str:
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        inflow = result.details.get("onchain_score", "N/A")
        lines = [
            "🐋 <b>고래 활동 감지</b>",
            f"심볼: {symbol}",
            f"온체인 점수: {inflow}",
            f"시간: {ts}",
            "",
            "휴면 고래 지갑이 활성화되었습니다. 큰 움직임에 주의하세요.",
        ]
        return "\n".join(lines)

    def periodic_report(self, symbol: str, result: AggregatedResult) -> str:
        """12h 정기 리포트 — 파생상품/감성 포함."""
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details

        lines = [
            f"📊 <b>변동성 분석 리포트</b> — {symbol}",
            f"🕐 {ts}",
            "",
            f"<b>종합 점수</b>: {result.final_score:.1f}/100 | <b>알림 레벨</b>: {result.alert_level}",
            "",
            "<b>기술적 분석</b>",
            f"  점수: {d.get('technical_score', 0):.1f} | 시그널: {d.get('technical_signal','')}",
            "",
            "<b>온체인</b>",
            f"  점수: {d.get('onchain_score', 0):.1f} | 시그널: {d.get('onchain_signal','')}",
            "",
            "<b>감성</b>",
            f"  점수: {d.get('sentiment_score', 0):.1f} | 시그널: {d.get('sentiment_signal','')}",
        ]

        # 파생상품 데이터가 있으면 추가
        if "derivatives_signal" in d:
            oi_chg = d.get("oi_3d_chg_pct", 0.0)
            fr = d.get("funding_rate", 0.0)
            lines += [
                "",
                "<b>파생상품</b>",
                f"  OI 3일: {oi_chg:+.1f}% | FR: {_fr_pct(fr)} | 시그널: {d.get('derivatives_signal','')}",
            ]

        lines += ["", f"💡 {_RECOMMENDATIONS.get(result.alert_level, '')}"]
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
