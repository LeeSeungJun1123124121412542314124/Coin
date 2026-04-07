"""방문자 카운터 API — 탭 접근 시 호출."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/visitor-ping")
async def visitor_ping():
    """방문자 카운터 증가 (오늘 + 누적)."""
    today = date.today().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT today_count, total_count FROM visitors WHERE date = ?", (today,)
        ).fetchone()

        if row:
            conn.execute(
                """UPDATE visitors
                   SET today_count = today_count + 1,
                       total_count = total_count + 1
                   WHERE date = ?""",
                (today,),
            )
            today_count = row["today_count"] + 1
            total_count = row["total_count"] + 1
        else:
            # 어제 total 가져와서 이어받기
            yesterday = conn.execute(
                "SELECT total_count FROM visitors ORDER BY date DESC LIMIT 1"
            ).fetchone()
            base_total = (yesterday["total_count"] if yesterday else 0) + 1

            conn.execute(
                """INSERT INTO visitors (date, today_count, total_count)
                   VALUES (?, 1, ?)""",
                (today, base_total),
            )
            today_count = 1
            total_count = base_total

    return JSONResponse({"today": today_count, "total": total_count, "date": today})


@router.get("/visitor-count")
async def get_visitor_count():
    """오늘 방문자 + 누적 방문자 조회."""
    today = date.today().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT today_count, total_count FROM visitors WHERE date = ?", (today,)
        ).fetchone()

        if not row:
            # 누적만 가져옴
            last = conn.execute(
                "SELECT total_count FROM visitors ORDER BY date DESC LIMIT 1"
            ).fetchone()
            return JSONResponse({
                "today": 0,
                "total": last["total_count"] if last else 0,
                "date": today,
            })

    return JSONResponse({
        "today": row["today_count"],
        "total": row["total_count"],
        "date": today,
    })
