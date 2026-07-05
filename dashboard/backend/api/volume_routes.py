"""볼륨 트래커 API 라우터 — 탭 2."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.upbit import fetch_krw_volume as upbit_volume
from dashboard.backend.collectors.bithumb import fetch_krw_volume as bithumb_volume
from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _kst_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_stock_fear_greed_stale(updated_at: str | None) -> bool:
    parsed = _parse_utc_datetime(updated_at)
    if parsed is None:
        return True
    return (_utc_now() - parsed).total_seconds() > 7200


def _is_kr_market_volume_stale(latest_date: str | None) -> bool:
    if latest_date is None:
        return True
    try:
        parsed = date.fromisoformat(latest_date)
    except ValueError:
        return True
    return (_kst_today() - parsed).days > 4


def _is_putcall_stale(updated_at: str | None) -> bool:
    parsed = _parse_utc_datetime(updated_at)
    if parsed is None:
        return True
    return (_utc_now() - parsed).total_seconds() > 172800


def _get_volume_history(days: int = 60) -> list[dict]:
    """volume_daily 테이블에서 최근 N일 데이터 조회."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, upbit_krw, bithumb_krw, crypto_ratio
               FROM volume_daily
               ORDER BY date DESC
               LIMIT ?""",
            (days,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


@router.get("/volume/stock-fear-greed")
async def get_stock_fear_greed():
    """미국 주식 Fear & Greed 최신 DB 데이터를 제공한다."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT value, rating, updated_at
               FROM stock_fear_greed
               ORDER BY date DESC
               LIMIT 1"""
        ).fetchone()

    if row is None:
        return JSONResponse({
            "value": None,
            "rating": None,
            "updated_at": None,
            "stale": True,
        })

    return JSONResponse({
        "value": row["value"],
        "rating": row["rating"],
        "updated_at": row["updated_at"],
        "stale": _is_stock_fear_greed_stale(row["updated_at"]),
    })


@router.get("/volume/kr-market-volume")
async def get_kr_market_volume(days: int = Query(30, ge=1, le=30)):
    """KOSPI/KOSDAQ 일별 거래대금 최신 DB 데이터를 제공한다."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, kospi_value, kosdaq_value
               FROM kr_market_volume
               WHERE kospi_value IS NOT NULL
                 AND kosdaq_value IS NOT NULL
               ORDER BY date DESC
               LIMIT ?""",
            (days,),
        ).fetchall()

    records = [
        {
            "date": row["date"],
            "kospi_value": row["kospi_value"],
            "kosdaq_value": row["kosdaq_value"],
        }
        for row in reversed(rows)
    ]
    latest_date = records[-1]["date"] if records else None
    return JSONResponse({
        "stale": _is_kr_market_volume_stale(latest_date),
        "records": records,
    })


@router.get("/volume/putcall")
async def get_putcall(days: int = Query(90, ge=1, le=90)):
    """CBOE Put/Call 비율 일별 DB 데이터를 제공한다."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, total_pc, equity_pc, index_pc, updated_at
               FROM cboe_putcall
               ORDER BY date DESC
               LIMIT ?""",
            (days,),
        ).fetchall()

    records = [
        {
            "date": row["date"],
            "total_pc": row["total_pc"],
            "equity_pc": row["equity_pc"],
            "index_pc": row["index_pc"],
        }
        for row in reversed(rows)
    ]
    latest_updated_at = rows[0]["updated_at"] if rows else None
    return JSONResponse({
        "stale": _is_putcall_stale(latest_updated_at),
        "records": records,
    })


def _calc_btc_rsi(ohlcv_days: int = 70, rsi_period: int = 14) -> list[dict]:
    """봇의 DataCollector로 BTC OHLCV 가져와 RSI 계산."""
    try:
        import asyncio as _asyncio
        from app.data.data_collector import DataCollector

        loop = _asyncio.get_event_loop()
        collector = DataCollector()
        loop.run_in_executor(None, collector.fetch_ohlcv, "BTC/USDT", "1d", ohlcv_days)
        # run_in_executor는 코루틴이므로 await 필요 — 여기서는 동기 컨텍스트
        # volume_routes는 async 함수에서 호출되므로 별도 처리
        return []
    except Exception as e:
        logger.error("BTC RSI 동기 조회 실패: %s", e)
        return []


async def _calc_btc_rsi_async(timeframe: str = "1d", days: int = 70) -> list[dict]:
    """비동기로 BTC RSI 계산."""
    try:
        from app.data.data_collector import DataCollector
        from app.analyzers.indicators.rsi import calculate as calc_rsi

        loop = asyncio.get_event_loop()
        collector = DataCollector()
        df = await loop.run_in_executor(
            None, collector.fetch_ohlcv, "BTC/USDT", timeframe, days
        )

        if df is None or df.empty:
            return []

        result = calc_rsi(df, period=14)
        rsi_series: pd.Series = result.get("rsi_series")
        if rsi_series is None or rsi_series.empty:
            return []

        # 날짜와 RSI 값 매핑
        rsi_list = []
        for idx, val in rsi_series.items():
            if pd.isna(val):
                continue
            date_str = str(idx)[:10] if hasattr(idx, '__str__') else str(idx)
            # df index가 datetime인 경우
            if hasattr(idx, 'date'):
                date_str = idx.date().isoformat()
            rsi_list.append({"date": date_str, "rsi": round(float(val), 2)})

        return rsi_list[-days:]

    except Exception as e:
        logger.error("BTC RSI 비동기 계산 실패 (%s): %s", timeframe, e)
        return []


@router.get("/volume-data")
async def get_volume_data():
    """볼륨 트래커 메인 데이터 — 현재 거래량 + 60일 히스토리."""
    # 실시간 거래량 (병렬)
    upbit_now, bithumb_now = await asyncio.gather(
        upbit_volume(),
        bithumb_volume(),
        return_exceptions=True,
    )

    if isinstance(upbit_now, Exception):
        upbit_now = None
    if isinstance(bithumb_now, Exception):
        bithumb_now = None

    upbit_val = upbit_now if isinstance(upbit_now, (int, float)) else None
    bithumb_val = bithumb_now if isinstance(bithumb_now, (int, float)) else None
    total_now = (upbit_val or 0) + (bithumb_val or 0)

    # DB 히스토리
    history = _get_volume_history(60)

    # 평균 (히스토리 기준)
    upbit_vals = [r["upbit_krw"] for r in history if r["upbit_krw"]]
    bithumb_vals = [r["bithumb_krw"] for r in history if r["bithumb_krw"]]
    avg_upbit = round(sum(upbit_vals) / len(upbit_vals), 4) if upbit_vals else None
    avg_bithumb = round(sum(bithumb_vals) / len(bithumb_vals), 4) if bithumb_vals else None

    return JSONResponse({
        "current": {
            "upbit_krw": upbit_val,
            "bithumb_krw": bithumb_val,
            "total_krw": round(total_now, 4) if total_now else None,
        },
        "avg_30d": {
            "upbit_krw": avg_upbit,
            "bithumb_krw": avg_bithumb,
        },
        "history": history,
    })


@router.get("/volume-weekly")
async def get_volume_weekly():
    """주간 합산 거래량 (최근 12주)."""
    history = _get_volume_history(90)

    if not history:
        return JSONResponse({"weeks": []})

    # 주간 그룹핑 (월요일 기준)
    from datetime import date as dt_date

    weekly: dict[str, dict] = {}
    for row in history:
        try:
            d = dt_date.fromisoformat(row["date"])
            # ISO 주차 기준 (YYYY-Www)
            week_key = d.strftime("%Y-W%W")
            if week_key not in weekly:
                weekly[week_key] = {"week": week_key, "upbit_krw": 0.0, "bithumb_krw": 0.0, "count": 0}
            weekly[week_key]["upbit_krw"] += row.get("upbit_krw") or 0
            weekly[week_key]["bithumb_krw"] += row.get("bithumb_krw") or 0
            weekly[week_key]["count"] += 1
        except Exception:
            continue

    weeks = sorted(weekly.values(), key=lambda x: x["week"])[-12:]
    for w in weeks:
        w["total_krw"] = round(w["upbit_krw"] + w["bithumb_krw"], 4)
        w["upbit_krw"] = round(w["upbit_krw"], 4)
        w["bithumb_krw"] = round(w["bithumb_krw"], 4)
        del w["count"]

    return JSONResponse({"weeks": weeks})


@router.get("/btc-weekly-rsi")
async def get_btc_weekly_rsi():
    """BTC 주봉 RSI (최근 52주)."""
    rsi_data = await _calc_btc_rsi_async("1w", 70)
    return JSONResponse({"rsi": rsi_data})


@router.get("/btc-daily-rsi")
async def get_btc_daily_rsi():
    """BTC 일봉 RSI (최근 60일)."""
    rsi_data = await _calc_btc_rsi_async("1d", 74)  # 14 warm-up + 60
    # 마지막 60개만
    return JSONResponse({"rsi": rsi_data[-60:] if len(rsi_data) > 60 else rsi_data})


@router.get("/fear-greed-history")
async def get_fear_greed_history():
    """공포탐욕 지수 히스토리 (Alternative.me, 최근 30일)."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.alternative.me/fng/",
                params={"limit": 30, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()

        entries = data.get("data", [])
        result = []
        for e in reversed(entries):  # 오래된 순
            result.append({
                "date": e.get("timestamp", "")[:10] if len(e.get("timestamp", "")) >= 10 else e.get("timestamp"),
                "value": int(e.get("value", 0)),
                "label": e.get("value_classification", ""),
            })

        # timestamp가 unix epoch인 경우 변환
        import datetime
        for item in result:
            ts = item["date"]
            if ts and ts.isdigit():
                item["date"] = datetime.datetime.fromtimestamp(int(ts)).date().isoformat()

        return JSONResponse({"history": result})

    except Exception as e:
        logger.error("공포탐욕 히스토리 조회 실패: %s", e)
        return JSONResponse({"history": []})
