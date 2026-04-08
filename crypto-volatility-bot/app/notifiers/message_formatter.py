"""Message formatter — 4 alert types for Telegram."""

from __future__ import annotations

from typing import Any

from app.analyzers.score_aggregator import AggregatedResult

_RECOMMENDATIONS = {
    "EMERGENCY": "⚠️ 즉각 포트폴리오 점검 필요. 리스크 관리 최우선.",
    "HIGH": "📊 높은 변동성. 포지션 크기 줄이고 손절선 설정 권장.",
    "MEDIUM": "📈 보통 변동성. 시장 모니터링 유지.",
    "LOW": "✅ 낮은 변동성. 안정적인 시장 상황.",
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
}


class MessageFormatter:
    def periodic_report(self, symbol: str, result: AggregatedResult) -> str:
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        d = result.details
        rec = _RECOMMENDATIONS.get(result.alert_level, "")
        lines = [
            f"📊 <b>변동성 분석 리포트</b> — {symbol}",
            f"🕐 {ts}",
            "",
            f"<b>종합 점수</b>: {result.final_score:.1f}/100",
            f"<b>알림 레벨</b>: {result.alert_level}",
            "",
            "<b>세부 점수</b>",
            f"  • 온체인:    {d.get('onchain_score', 0):.1f} ({d.get('onchain_signal','')})",
            f"  • 기술적:    {d.get('technical_score', 0):.1f} ({d.get('technical_signal','')})",
            f"  • 감성:      {d.get('sentiment_score', 0):.1f} ({d.get('sentiment_signal','')})",
            "",
            f"💡 {rec}",
        ]
        return "\n".join(lines)

    def emergency_alert(self, symbol: str, result: AggregatedResult) -> str:
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "🚨 <b>긴급 변동성 경보</b> 🚨",
            f"심볼: {symbol}",
            f"점수: <b>{result.final_score:.1f}/100</b> (EMERGENCY)",
            f"시간: {ts}",
            "",
            _RECOMMENDATIONS["EMERGENCY"],
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
