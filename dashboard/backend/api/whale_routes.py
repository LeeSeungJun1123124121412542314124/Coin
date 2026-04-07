"""고래 추적 API 라우터 — 탭 8."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from dashboard.backend.collectors.hyperliquid import (
    fetch_leaderboard, fetch_user_positions, fetch_top_whale_positions,
)
from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


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
        return JSONResponse({"error": "포지션 조회 실패"}, status_code=404)
    return JSONResponse(pos)


@router.get("/whale-consensus")
async def get_whale_consensus(top_n: int = Query(10, ge=5, le=20)):
    """TOP N 고래들의 BTC 포지션 방향 합의.

    Returns:
      {long_count, short_count, neutral_count, consensus: 'long'|'short'|'neutral'}
    """
    whales = await fetch_leaderboard(top_n)
    if not whales:
        return JSONResponse({"error": "데이터 없음"}, status_code=503)

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
