"""고래 추적 API 라우터 — 탭 8."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.hyperliquid import (
    fetch_leaderboard, fetch_user_positions, fetch_top_whale_positions,
)
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.errors import api_error

logger = logging.getLogger(__name__)
router = APIRouter()


def _kst_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _is_kr_investor_flow_stale(latest_date: str | None) -> bool:
    if latest_date is None:
        return True
    try:
        parsed = date.fromisoformat(latest_date)
    except ValueError:
        return True
    return (_kst_today() - parsed).days > 4


@router.get("/hyperliquid-whales")
async def get_whales(top_n: int = Query(10, ge=5, le=20)):
    """HL 고래 리더보드 + 현재 포지션 (실시간)."""
    whales = await fetch_top_whale_positions(top_n)

    # BTC 포지션만 요약
    for w in whales:
        btc_pos = next(
            (p for p in w.get("positions", []) if p["coin"] in ("BTC", "BTCUSDT")),
            None,
        )
        w["btc_position"] = btc_pos

    return JSONResponse({"whales": whales, "total": len(whales)})


@router.get("/whale-history")
async def get_whale_history(limit: int = Query(50, ge=10, le=200)):
    """DB에서 최근 고래 스냅샷 히스토리 조회."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT captured_at, address, nickname, account_value, pnl, roi, positions
               FROM whale_snapshots
               ORDER BY captured_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    result = []
    for row in rows:
        r = dict(row)
        try:
            r["positions"] = json.loads(r["positions"] or "[]")
        except Exception:
            r["positions"] = []
        result.append(r)

    return JSONResponse({"history": result})


@router.get("/whale-position/{address}")
async def get_whale_position(address: str):
    """특정 고래 주소의 현재 포지션 상세."""
    pos = await fetch_user_positions(address)
    if pos is None:
        return api_error(404, "WHALE_NOT_FOUND", "포지션 조회 실패")
    return JSONResponse(pos)


@router.get("/whale-consensus")
async def get_whale_consensus(top_n: int = Query(10, ge=5, le=20)):
    """TOP N 고래들의 BTC 포지션 방향 합의.

    Returns:
      {long_count, short_count, neutral_count, consensus: 'long'|'short'|'neutral'}
    """
    whales = await fetch_leaderboard(top_n)
    if not whales:
        return api_error(503, "WHALE_UNAVAILABLE", "데이터 없음")

    # DB에서 최신 스냅샷 기반 합의
    with get_db() as conn:
        # 최근 2시간 이내 스냅샷
        rows = conn.execute(
            """SELECT nickname, address, positions
               FROM whale_snapshots
               WHERE captured_at >= datetime('now', '-2 hours')
               ORDER BY captured_at DESC""",
        ).fetchall()

    long_count = short_count = neutral_count = 0
    seen = set()

    for row in rows:
        addr = row["address"]
        if addr in seen:
            continue
        seen.add(addr)

        try:
            positions = json.loads(row["positions"] or "[]")
        except Exception:
            positions = []

        btc_pos = next(
            (p for p in positions if p.get("coin") in ("BTC", "BTCUSDT")),
            None,
        )

        if btc_pos is None:
            neutral_count += 1
        elif btc_pos.get("side") == "long":
            long_count += 1
        else:
            short_count += 1

    total = long_count + short_count + neutral_count
    if total == 0:
        consensus = "unknown"
    elif long_count > short_count + neutral_count:
        consensus = "long"
    elif short_count > long_count + neutral_count:
        consensus = "short"
    else:
        consensus = "neutral"

    return JSONResponse({
        "long_count": long_count,
        "short_count": short_count,
        "neutral_count": neutral_count,
        "total": total,
        "consensus": consensus,
        "long_pct": round(long_count / total * 100, 1) if total else 0,
        "short_pct": round(short_count / total * 100, 1) if total else 0,
    })


_US_INSIDER_WINDOW_DAYS = 90   # 표시 창 — 수집 job의 _LOOKBACK_DAYS와 동일
_US_INSIDER_TRADES_LIMIT = 50


@router.get("/whale/us-insider-trades")
async def get_us_insider_trades():
    """미국 관심종목 슬롯의 내부자 매매(Form 4) — 종목별 90일 합산 + 최근 거래 목록."""
    since = (date.today() - timedelta(days=_US_INSIDER_WINDOW_DAYS)).isoformat()

    with get_db() as conn:
        slots = conn.execute(
            "SELECT ticker, name FROM stock_slots WHERE market='us' ORDER BY position"
        ).fetchall()
        tickers = [slot["ticker"].upper() for slot in slots]
        placeholders = ",".join("?" for _ in tickers) or "''"

        summary_rows = conn.execute(
            f"""SELECT ticker,
                       SUM(CASE WHEN code='P' THEN value ELSE 0 END) AS buy_value,
                       SUM(CASE WHEN code='S' THEN value ELSE 0 END) AS sell_value,
                       COUNT(*) AS trade_count
                FROM us_insider_trades
                WHERE transaction_date >= ? AND ticker IN ({placeholders})
                GROUP BY ticker""",
            (since, *tickers),
        ).fetchall()
        trade_rows = conn.execute(
            f"""SELECT ticker, transaction_date, filed_at, insider_name, insider_title,
                       code, shares, price, value
                FROM us_insider_trades
                WHERE transaction_date >= ? AND ticker IN ({placeholders})
                ORDER BY transaction_date DESC, filed_at DESC
                LIMIT ?""",
            (since, *tickers, _US_INSIDER_TRADES_LIMIT),
        ).fetchall()

    by_ticker = {row["ticker"]: row for row in summary_rows}
    summaries = []
    for slot in slots:
        ticker = slot["ticker"].upper()
        row = by_ticker.get(ticker)
        buy_value = (row["buy_value"] if row else 0.0) or 0.0
        sell_value = (row["sell_value"] if row else 0.0) or 0.0
        summaries.append({
            "ticker": ticker,
            "name": slot["name"],
            "buy_value": buy_value,
            "sell_value": sell_value,
            "net_value": buy_value + sell_value,
            "trade_count": row["trade_count"] if row else 0,
        })

    return JSONResponse({
        "summaries": summaries,
        "trades": [dict(row) for row in trade_rows],
    })


@router.get("/whale/kr-investor-flow")
async def get_kr_investor_flow(
    market: str = Query("KOSPI", pattern="^(KOSPI|KOSDAQ)$"),
    days: int = Query(30, ge=1, le=30),
):
    """한국 시장 투자자별 순매수 흐름을 DB의 마지막 성공 데이터로 제공한다."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, foreign_net, institution_net, individual_net
               FROM kr_investor_flow
               WHERE market = ?
               ORDER BY date DESC
               LIMIT ?""",
            (market, days),
        ).fetchall()

    records = [
        {
            "date": row["date"],
            "foreign_net": row["foreign_net"],
            "institution_net": row["institution_net"],
            "individual_net": row["individual_net"],
        }
        for row in reversed(rows)
    ]
    latest_date = records[-1]["date"] if records else None
    return JSONResponse({
        "market": market,
        "stale": _is_kr_investor_flow_stale(latest_date),
        "records": records,
    })
