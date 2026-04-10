"""GET /api/alerts — 알림 히스토리 조회."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/alerts/history")
async def get_alert_history(limit: int = 50, symbol: str | None = None):
    """알림 발송 히스토리 조회.

    Args:
        limit: 최대 반환 건수 (기본 50)
        symbol: 특정 심볼 필터 (없으면 전체)
    """
    try:
        with get_db() as conn:
            if symbol:
                rows = conn.execute(
                    """SELECT id, timestamp, symbol, alert_level, alert_score,
                              final_score, details, message_sent
                       FROM alert_history
                       WHERE symbol = ?
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (symbol.upper(), min(limit, 200)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, timestamp, symbol, alert_level, alert_score,
                              final_score, details, message_sent
                       FROM alert_history
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (min(limit, 200),),
                ).fetchall()

        result = [
            {
                "id": row[0],
                "timestamp": row[1],
                "symbol": row[2],
                "alert_level": row[3],
                "alert_score": row[4],
                "final_score": row[5],
                "details": row[6],
                "message_sent": bool(row[7]),
            }
            for row in rows
        ]
        return JSONResponse({"alerts": result, "total": len(result)})
    except Exception as e:
        logger.error("알림 히스토리 조회 실패: %s", e)
        return JSONResponse({"alerts": [], "total": 0})
