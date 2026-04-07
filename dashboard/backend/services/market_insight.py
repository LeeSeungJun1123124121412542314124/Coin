"""시장 인사이트 서비스 — 룰 기반 자동 인사이트 생성.

탭 5 시장 분석에서 사용.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── 인사이트 등급 ────────────────────────────────────────────────
LEVEL_CRITICAL = "critical"  # 즉각 대응 필요
LEVEL_WARNING  = "warning"   # 주의 필요
LEVEL_NEUTRAL  = "neutral"   # 중립
LEVEL_BULLISH  = "bullish"   # 상승 우호
LEVEL_BEARISH  = "bearish"   # 하락 경고


def generate_insights(dashboard_data: dict[str, Any]) -> list[dict]:
    """대시보드 데이터에서 룰 기반 인사이트 목록 생성."""
    insights: list[dict] = []

    try:
        _check_fear_greed(insights, dashboard_data)
        _check_vix(insights, dashboard_data)
        _check_kimchi_premium(insights, dashboard_data)
        _check_btc_dominance(insights, dashboard_data)
        _check_funding_rate(insights, dashboard_data)
        _check_oi_change(insights, dashboard_data)
        _check_us_market(insights, dashboard_data)
    except Exception as e:
        logger.error("인사이트 생성 오류: %s", e)

    # 중요도 순 정렬: critical > warning > bearish > bullish > neutral
    _order = {LEVEL_CRITICAL: 0, LEVEL_WARNING: 1, LEVEL_BEARISH: 2, LEVEL_BULLISH: 3, LEVEL_NEUTRAL: 4}
    insights.sort(key=lambda x: _order.get(x.get("level", LEVEL_NEUTRAL), 4))

    return insights


def _insight(level: str, title: str, body: str, icon: str = "•") -> dict:
    return {"level": level, "title": title, "body": body, "icon": icon}


# ─── 개별 룰 ─────────────────────────────────────────────────────

def _check_fear_greed(insights: list, data: dict) -> None:
    fg = data.get("fear_greed")
    if not fg:
        return
    value = fg.get("value")
    label = fg.get("label", "")
    if value is None:
        return

    if value <= 20:
        insights.append(_insight(LEVEL_BULLISH, "극도 공포 — 역투자 기회",
            f"공포탐욕 {value}pt ({label}). 역사적으로 극도 공포 구간은 중기 매수 기회.", "🟢"))
    elif value <= 40:
        insights.append(_insight(LEVEL_NEUTRAL, "공포 구간",
            f"공포탐욕 {value}pt ({label}). 시장 심리 위축 상태.", "⚪"))
    elif value >= 80:
        insights.append(_insight(LEVEL_WARNING, "극도 탐욕 — 과열 경고",
            f"공포탐욕 {value}pt ({label}). 단기 조정 가능성 증가.", "🔴"))
    elif value >= 65:
        insights.append(_insight(LEVEL_NEUTRAL, "탐욕 구간",
            f"공포탐욕 {value}pt ({label}). 추세 지속 여부 모니터링.", "🟡"))


def _check_vix(insights: list, data: dict) -> None:
    us = data.get("us_market", {})
    vix = us.get("^VIX", {}).get("price")
    if vix is None:
        return

    if vix >= 30:
        insights.append(_insight(LEVEL_CRITICAL, f"VIX 급등 — 공포 지수 {vix:.1f}",
            "미국 증시 극단적 변동성 구간. 크립토 연동 하락 위험.", "🚨"))
    elif vix >= 20:
        insights.append(_insight(LEVEL_WARNING, f"VIX 주의 — {vix:.1f}",
            "미국 증시 변동성 상승. 리스크 자산 전반 주의.", "⚠️"))
    elif vix < 13:
        insights.append(_insight(LEVEL_BULLISH, f"VIX 저점 — {vix:.1f} (안정)",
            "미국 증시 변동성 극히 낮음. 위험 선호 환경.", "🟢"))


def _check_kimchi_premium(insights: list, data: dict) -> None:
    kp = data.get("kimchi_premium")
    if kp is None:
        return

    if kp >= 5.0:
        insights.append(_insight(LEVEL_WARNING, f"김치 프리미엄 과열 — {kp:.2f}%",
            "국내 거래소 과매수 신호. 해외 차익거래 유입 주의.", "🌶️"))
    elif kp >= 3.0:
        insights.append(_insight(LEVEL_NEUTRAL, f"김치 프리미엄 상승 — {kp:.2f}%",
            "국내 수요 우위 상태.", "🟡"))
    elif kp <= -1.0:
        insights.append(_insight(LEVEL_BEARISH, f"역 김치 프리미엄 — {kp:.2f}%",
            "국내 투자 심리 위축 또는 외국인 매도. 단기 약세 신호.", "🔵"))


def _check_btc_dominance(insights: list, data: dict) -> None:
    onchain = data.get("onchain", {})
    dom = onchain.get("btc_dominance")
    if dom is None:
        return

    if dom >= 60:
        insights.append(_insight(LEVEL_BEARISH, f"BTC 도미넌스 고점 — {dom:.1f}%",
            "알트코인 약세 장 지속 가능성. 비트코인 우선 전략.", "📊"))
    elif dom <= 45:
        insights.append(_insight(LEVEL_BULLISH, f"BTC 도미넌스 저점 — {dom:.1f}%",
            "알트코인 시즌 진입 가능성. 알트 모멘텀 주시.", "🚀"))


def _check_funding_rate(insights: list, data: dict) -> None:
    deriv = data.get("derivatives", {})
    fr = deriv.get("funding_rate")
    if fr is None:
        return

    # fr은 비율 (예: 0.0003 = 0.03%)
    fr_pct = fr * 100

    if fr_pct >= 0.05:
        insights.append(_insight(LEVEL_WARNING, f"펀딩비 과열 — {fr_pct:.4f}%",
            "선물 롱 포지션 과밀집. 숏 스퀴즈 또는 급락 위험.", "⚠️"))
    elif fr_pct <= -0.02:
        insights.append(_insight(LEVEL_BULLISH, f"펀딩비 마이너스 — {fr_pct:.4f}%",
            "숏 포지션 우위. 반등 시 숏 커버 상승 가능.", "🟢"))


def _check_oi_change(insights: list, data: dict) -> None:
    deriv = data.get("derivatives", {})
    oi_change = deriv.get("oi_change_3d")
    if oi_change is None:
        return

    pct = oi_change * 100

    if pct >= 20:
        insights.append(_insight(LEVEL_CRITICAL, f"OI 급등 — 3일 +{pct:.1f}%",
            "미결제약정 급격 증가. 변동성 확대 임박 가능성.", "🚨"))
    elif pct >= 10:
        insights.append(_insight(LEVEL_WARNING, f"OI 상승 — 3일 +{pct:.1f}%",
            "레버리지 축적 진행 중. 포지션 청산 위험 주의.", "⚠️"))
    elif pct <= -10:
        insights.append(_insight(LEVEL_NEUTRAL, f"OI 감소 — 3일 {pct:.1f}%",
            "포지션 정리 구간. 변동성 축소 또는 방향 전환 신호.", "⚪"))


def _check_us_market(insights: list, data: dict) -> None:
    us = data.get("us_market", {})

    # 나스닥 상태
    qqq = us.get("^IXIC", {})
    nasdaq_chg = qqq.get("change_pct")
    if nasdaq_chg is not None:
        if nasdaq_chg <= -2.0:
            insights.append(_insight(LEVEL_WARNING, f"나스닥 급락 — {nasdaq_chg:+.2f}%",
                "미국 성장주 매도 압력. 크립토 동반 하락 주의.", "📉"))
        elif nasdaq_chg >= 2.0:
            insights.append(_insight(LEVEL_BULLISH, f"나스닥 강세 — {nasdaq_chg:+.2f}%",
                "위험 선호 심리 회복. 크립토 동반 상승 기대.", "📈"))

    # DXY (달러 인덱스)
    dxy = us.get("DX-Y.NYB", {})
    dxy_price = dxy.get("price")
    dxy_chg = dxy.get("change_pct")
    if dxy_price is not None and dxy_chg is not None:
        if dxy_chg >= 0.5 and dxy_price >= 104:
            insights.append(_insight(LEVEL_BEARISH, f"달러 강세 — DXY {dxy_price:.1f} ({dxy_chg:+.2f}%)",
                "강달러 환경. 크립토/원자재 전반 약세 압력.", "💵"))
        elif dxy_chg <= -0.5:
            insights.append(_insight(LEVEL_BULLISH, f"달러 약세 — DXY {dxy_price:.1f} ({dxy_chg:+.2f}%)",
                "달러 약세. 리스크 자산 상승 우호 환경.", "🟢"))
