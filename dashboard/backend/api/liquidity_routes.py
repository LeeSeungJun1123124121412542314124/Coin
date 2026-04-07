"""유동성 API 라우터 — 탭 6.

TGA, M2, SOMA (FRED), 국채 경매 (TreasuryDirect).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.fred import (
    fetch_tga, fetch_m2, fetch_soma,
    calc_tga_yoy, calc_m2_yoy,
)
from dashboard.backend.collectors.treasury import (
    fetch_upcoming_auctions, fetch_recent_auctions,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/liquidity-summary")
async def get_liquidity_summary():
    """유동성 요약 — TGA 현재값 + M2 YoY + SOMA."""
    tga_data, m2_data, soma_data = await asyncio.gather(
        fetch_tga(104),
        fetch_m2(60),
        fetch_soma(52),
        return_exceptions=True,
    )

    tga_current = None
    tga_7d_change = None
    if isinstance(tga_data, list) and tga_data:
        tga_current = tga_data[-1]["value"]
        if len(tga_data) >= 2:
            tga_7d_change = tga_data[-1]["value"] - tga_data[-2]["value"]

    m2_current = None
    m2_yoy = None
    if isinstance(m2_data, list) and m2_data:
        m2_current = m2_data[-1]["value"]
        m2_with_yoy = calc_m2_yoy(m2_data)
        if m2_with_yoy:
            m2_yoy = m2_with_yoy[-1]["yoy_pct"]

    soma_current = None
    soma_7d_change = None
    if isinstance(soma_data, list) and soma_data:
        soma_current = soma_data[-1]["value"] / 1e6  # 백만 → 조 (십억 달러 단위)
        if len(soma_data) >= 2:
            soma_7d_change = (soma_data[-1]["value"] - soma_data[-2]["value"]) / 1e6

    # 유동성 방향 판단
    direction = _assess_liquidity_direction(tga_7d_change, m2_yoy, soma_7d_change)

    return JSONResponse({
        "tga": {
            "current_b": tga_current,
            "7d_change_b": round(tga_7d_change, 2) if tga_7d_change is not None else None,
            "direction": "supply" if (tga_7d_change or 0) < 0 else "drain",
        },
        "m2": {
            "current_b": m2_current,
            "yoy_pct": m2_yoy,
        },
        "soma": {
            "current_b": round(soma_current, 2) if soma_current else None,
            "7d_change_b": round(soma_7d_change, 2) if soma_7d_change is not None else None,
        },
        "overall_direction": direction,
    })


@router.get("/tga-history")
async def get_tga_history():
    """TGA + YoY 히스토리 (최근 2년)."""
    tga_data = await fetch_tga(104)
    tga_yoy = calc_tga_yoy(tga_data)

    # BTC 가격 병합 (있으면)
    btc_map = await _get_btc_weekly_prices()

    result = []
    for row in tga_yoy[-52:]:  # 최근 1년
        result.append({
            "date": row["date"],
            "tga_b": row["value"],
            "yoy_pct": row["yoy_pct"],
            "btc": btc_map.get(row["date"]),
        })

    return JSONResponse({"history": result})


@router.get("/m2-history")
async def get_m2_history():
    """M2 YoY 히스토리 (최근 5년)."""
    m2_data = await fetch_m2(72)
    m2_yoy = calc_m2_yoy(m2_data)

    return JSONResponse({"history": m2_yoy[-48:]})  # 4년


@router.get("/soma-history")
async def get_soma_history():
    """SOMA 보유량 히스토리 (최근 2년)."""
    soma_data = await fetch_soma(104)
    result = [
        {"date": r["date"], "value_b": round(r["value"] / 1e6, 2)}
        for r in soma_data
    ]
    return JSONResponse({"history": result})


@router.get("/treasury-auctions")
async def get_treasury_auctions():
    """국채 경매 일정 (향후 4주 + 최근 완료)."""
    upcoming, recent = await asyncio.gather(
        fetch_upcoming_auctions(28),
        fetch_recent_auctions(15),
        return_exceptions=True,
    )

    return JSONResponse({
        "upcoming": upcoming if not isinstance(upcoming, Exception) else [],
        "recent": recent if not isinstance(recent, Exception) else [],
    })


# ─── 내부 헬퍼 ──────────────────────────────────────────────────

def _assess_liquidity_direction(
    tga_7d: float | None,
    m2_yoy: float | None,
    soma_7d: float | None,
) -> str:
    """유동성 방향 종합 판단."""
    signals = []
    if tga_7d is not None:
        signals.append("supply" if tga_7d < 0 else "drain")
    if m2_yoy is not None:
        signals.append("supply" if m2_yoy > 3.0 else "drain" if m2_yoy < 1.0 else "neutral")
    if soma_7d is not None:
        signals.append("supply" if soma_7d < 0 else "drain")

    if not signals:
        return "unknown"

    supply_count = signals.count("supply")
    drain_count = signals.count("drain")

    if supply_count > drain_count:
        return "supply"
    elif drain_count > supply_count:
        return "drain"
    return "neutral"


async def _get_btc_weekly_prices() -> dict[str, float]:
    """BTC 주간 종가 맵 {날짜: 가격}."""
    try:
        import asyncio as _asyncio
        from app.data.data_collector import DataCollector
        loop = _asyncio.get_event_loop()
        collector = DataCollector()
        df = await loop.run_in_executor(None, collector.fetch_ohlcv, "BTC/USDT", "1w", 55)
        if df is None or df.empty:
            return {}
        result = {}
        for idx, row in df.iterrows():
            date_str = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            result[date_str] = round(float(row["close"]), 2)
        return result
    except Exception:
        return {}
