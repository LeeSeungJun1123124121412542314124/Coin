"""시장 분석 API 라우터 — 탭 5."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.services.market_insight import generate_insights

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/market-analysis")
async def get_market_analysis():
    """탭 5 시장 분석 — 인사이트 + 핵심 지표 + VIX vs BTC 차트."""

    # 대시보드 데이터 재사용 (캐시 덕분에 비용 없음)
    dashboard_data = await _get_dashboard_snapshot()

    insights = generate_insights(dashboard_data)

    # VIX vs BTC 30일 히스토리 (야후 파이낸스)
    vix_btc = await _get_vix_btc_history()

    # 봇 최근 분석 레벨 (SPF 보정용과 동일)
    bot_level = _get_latest_bot_level()

    return JSONResponse({
        "insights": insights,
        "key_indicators": _build_key_indicators(dashboard_data),
        "vix_btc_history": vix_btc,
        "bot_level": bot_level,
    })


@router.get("/insights")
async def get_insights():
    """인사이트만 반환 (경량 엔드포인트)."""
    dashboard_data = await _get_dashboard_snapshot()
    insights = generate_insights(dashboard_data)
    return JSONResponse({"insights": insights})


# ─── 내부 헬퍼 ──────────────────────────────────────────────────

async def _get_dashboard_snapshot() -> dict:
    """대시보드 API 응답 재활용 (캐시 히트)."""
    from dashboard.backend.collectors.coingecko import fetch_prices, fetch_global
    from dashboard.backend.collectors.yahoo_finance import fetch_us_market
    from dashboard.backend.collectors.binance_derivatives import (
        fetch_open_interest, fetch_funding_rate,
    )
    from dashboard.backend.services.kimchi_premium import calc_kimchi_premium

    try:
        coins, global_data, us_market, oi, fr = await asyncio.gather(
            fetch_prices(),
            fetch_global(),
            fetch_us_market(),
            fetch_open_interest("BTCUSDT"),
            fetch_funding_rate("BTCUSDT"),
            return_exceptions=True,
        )
    except Exception as e:
        logger.error("대시보드 스냅샷 조회 실패: %s", e)
        return {}

    btc_price = None
    if isinstance(coins, list):
        btc = next((c for c in coins if c.get("symbol") == "BTC"), None)
        btc_price = btc["price"] if btc else None

    kimchi = None
    if btc_price:
        try:
            kimchi = await calc_kimchi_premium(btc_price)
        except Exception:
            pass

    fear_greed = await _get_fear_greed()

    # OI 3일 변화 (DB에서)
    oi_change_3d = _get_latest_oi_change()

    return {
        "coins": coins if isinstance(coins, list) else [],
        "global": global_data if not isinstance(global_data, Exception) else {},
        "us_market": us_market if not isinstance(us_market, Exception) else {},
        "derivatives": {
            "open_interest": oi if not isinstance(oi, Exception) else None,
            "funding_rate": fr if not isinstance(fr, Exception) else None,
            "oi_change_3d": oi_change_3d,
        },
        "kimchi_premium": kimchi,
        "fear_greed": fear_greed,
        "onchain": await _get_onchain(),
    }


async def _get_fear_greed() -> dict | None:
    from app.data.data_collector import DataCollector

    loop = asyncio.get_event_loop()
    try:
        collector = DataCollector()
        value = await loop.run_in_executor(None, collector.fetch_fear_greed)
        if value is None:
            return None
        labels = {(0,25): "극단적 공포", (26,50): "공포", (51,75): "탐욕", (76,100): "극단적 탐욕"}
        label = next((v for (lo,hi),v in labels.items() if lo <= value <= hi), "중립")
        return {"value": value, "label": label}
    except Exception as e:
        logger.error("Fear & Greed 조회 실패: %s", e)
        return None


async def _get_onchain() -> dict | None:
    from app.data.data_collector import DataCollector

    loop = asyncio.get_event_loop()
    try:
        collector = DataCollector()
        return await loop.run_in_executor(None, collector.fetch_onchain_data, "btc")
    except Exception as e:
        logger.error("온체인 데이터 조회 실패: %s", e)
        return None


def _get_latest_oi_change() -> float | None:
    """최근 spf_records에서 oi_change_3d 조회."""
    try:
        from dashboard.backend.db.connection import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT oi_change_3d FROM spf_records ORDER BY date DESC LIMIT 1"
            ).fetchone()
        return row["oi_change_3d"] if row else None
    except Exception:
        return None


def _get_latest_bot_level() -> str | None:
    """최근 봇 분석 alert_level 조회."""
    try:
        from dashboard.backend.db.connection import get_db
        with get_db() as conn:
            row = conn.execute(
                """SELECT alert_level FROM analysis_history
                   WHERE symbol = 'BTC/USDT'
                   ORDER BY timestamp DESC LIMIT 1"""
            ).fetchone()
        return row["alert_level"] if row else None
    except Exception:
        return None


def _build_key_indicators(data: dict) -> list[dict]:
    """주요 지표 카드 목록 빌드."""
    indicators = []

    fg = data.get("fear_greed") or {}
    if fg.get("value") is not None:
        indicators.append({
            "label": "공포탐욕",
            "value": fg["value"],
            "unit": "pt",
            "label2": fg.get("label", ""),
        })

    us = data.get("us_market") or {}
    vix = (us.get("^VIX") or {}).get("price")
    if vix is not None:
        indicators.append({"label": "VIX", "value": round(vix, 2), "unit": ""})

    dxy = (us.get("DX-Y.NYB") or {}).get("price")
    if dxy is not None:
        indicators.append({"label": "DXY", "value": round(dxy, 2), "unit": ""})

    kp = data.get("kimchi_premium")
    if kp is not None:
        indicators.append({"label": "김프", "value": round(kp, 2), "unit": "%"})

    deriv = data.get("derivatives") or {}
    fr = deriv.get("funding_rate")
    if fr is not None:
        indicators.append({"label": "펀딩비", "value": round(fr * 100, 4), "unit": "%"})

    oi_change = deriv.get("oi_change_3d")
    if oi_change is not None:
        indicators.append({"label": "OI 3일", "value": round(oi_change * 100, 2), "unit": "%"})

    onchain = data.get("onchain") or {}
    dom = onchain.get("btc_dominance")
    if dom is not None:
        indicators.append({"label": "BTC 도미넌스", "value": round(dom, 1), "unit": "%"})

    return indicators


async def _get_vix_btc_history() -> list[dict]:
    """VIX + BTC 가격 30일 히스토리 (야후파이낸스 + 봇 DataCollector)."""
    import asyncio as _asyncio
    from app.data.data_collector import DataCollector
    import httpx

    loop = _asyncio.get_event_loop()

    # BTC 일봉 OHLCV
    btc_task = loop.run_in_executor(
        None,
        lambda: _fetch_btc_ohlcv_sync(),
    )

    # VIX 히스토리 (yfinance)
    vix_task = loop.run_in_executor(
        None,
        lambda: _fetch_vix_history_sync(),
    )

    btc_data, vix_data = await _asyncio.gather(btc_task, vix_task, return_exceptions=True)

    if isinstance(btc_data, Exception) or isinstance(vix_data, Exception):
        return []

    # 날짜 기준 병합
    vix_map = {r["date"]: r["vix"] for r in (vix_data or [])}
    btc_map = {r["date"]: r["close"] for r in (btc_data or [])}

    dates = sorted(set(list(vix_map.keys()) + list(btc_map.keys())))[-30:]
    result = []
    for d in dates:
        result.append({
            "date": d,
            "vix": vix_map.get(d),
            "btc": btc_map.get(d),
        })

    return result


def _fetch_btc_ohlcv_sync() -> list[dict]:
    try:
        from app.data.data_collector import DataCollector
        collector = DataCollector()
        df = collector.fetch_ohlcv("BTC/USDT", "1d", 35)
        if df is None or df.empty:
            return []
        records = []
        for idx, row in df.iterrows():
            date_str = idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10]
            records.append({"date": date_str, "close": round(float(row["close"]), 2)})
        return records
    except Exception as e:
        logger.error("BTC OHLCV 조회 실패: %s", e)
        return []


def _fetch_vix_history_sync() -> list[dict]:
    try:
        import yfinance as yf
        ticker = yf.Ticker("^VIX")
        df = ticker.history(period="35d", interval="1d")
        if df is None or df.empty:
            return []
        records = []
        for idx, row in df.iterrows():
            date_str = idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10]
            records.append({"date": date_str, "vix": round(float(row["Close"]), 2)})
        return records
    except Exception as e:
        logger.error("VIX 히스토리 조회 실패: %s", e)
        return []
