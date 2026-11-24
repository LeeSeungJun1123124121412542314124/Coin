"""그록봇 리포트 수신·조회.

- POST /api/bot-reports : 봇이 보내는 리포트 수신. PIN 토큰 대신 X-Bot-Key 헤더(환경변수 BOT_INGEST_KEY)로 인증.
- GET  /api/bot-reports : 받은 리포트 목록. 다른 화면과 같은 PIN 토큰 인증(main.py에서 의존성으로 건다).

스펙: docs/plans/bot-reports-spec-2026-11-24.md
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from dashboard.backend.utils.limiter import limiter

logger = logging.getLogger(__name__)

KINDS = ("daily_check", "weekly_check", "heatmap", "whale", "breakout", "other")
_MAX_DATA_CHARS = 50_000

ingest_router = APIRouter()  # 봇 키 인증 (PIN 불필요)
router = APIRouter()         # PIN 토큰 인증


class BotReportIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: Literal["daily_check", "weekly_check", "heatmap", "whale", "breakout", "other"]
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    reported_at: datetime | None = None
    data: dict | None = None

    @field_validator("data")
    @classmethod
    def _limit_data_size(cls, value: dict | None) -> dict | None:
        if value is not None and len(json.dumps(value, ensure_ascii=False)) > _MAX_DATA_CHARS:
            raise ValueError(f"data는 JSON으로 {_MAX_DATA_CHARS}자 이하여야 합니다")
        return value


def _check_bot_key(request: Request) -> None:
    expected = os.getenv("BOT_INGEST_KEY", "")
    if not expected:
        # 키를 등록하기 전에는 수신 자체를 끈다 — 빈 키와 빈 헤더가 일치해 통과하는 일을 막는다
        raise HTTPException(status_code=503, detail="봇 리포트 수신이 설정되지 않았습니다")
    given = request.headers.get("X-Bot-Key", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="봇 키가 올바르지 않습니다")


@ingest_router.post("/bot-reports")
@limiter.limit("30/minute")
async def receive_bot_report(request: Request, report: BotReportIn) -> JSONResponse:
    """리포트 1건 수신. 같은 kind·title·body를 다시 보내면 새로 저장하지 않는다."""
    # 키 검사를 요청 제한 안쪽에서 한다 — 틀린 키로 반복 시도하는 것도 제한에 걸리게
    _check_bot_key(request)
    from dashboard.backend.db import connection

    now = datetime.now(timezone.utc).isoformat()
    reported = report.reported_at
    if reported is None:
        reported_at = now
    else:
        if reported.tzinfo is None:
            reported = reported.replace(tzinfo=timezone.utc)
        reported_at = reported.astimezone(timezone.utc).isoformat()
    content_hash = hashlib.sha256("\0".join((report.kind, report.title, report.body)).encode()).hexdigest()
    data_json = json.dumps(report.data, ensure_ascii=False) if report.data is not None else None

    with connection.get_db() as conn:
        existing = conn.execute("SELECT id FROM bot_reports WHERE content_hash = ?", (content_hash,)).fetchone()
        if existing:
            return JSONResponse({"ok": True, "id": existing["id"], "duplicate": True})
        cursor = conn.execute(
            """INSERT INTO bot_reports (kind, title, body, data_json, reported_at, received_at, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (report.kind, report.title, report.body, data_json, reported_at, now, content_hash),
        )
        report_id = cursor.lastrowid
    logger.info("봇 리포트 수신: id=%s kind=%s", report_id, report.kind)
    return JSONResponse({"ok": True, "id": report_id, "duplicate": False})


@router.get("/bot-reports")
async def list_bot_reports(kind: str | None = None, limit: int = 50) -> JSONResponse:
    """받은 리포트를 최신순으로 반환. kind로 거르고 limit(최대 200)으로 개수를 제한한다."""
    if kind is not None and kind not in KINDS:
        raise HTTPException(status_code=422, detail="알 수 없는 kind입니다")
    from dashboard.backend.db import connection

    where = "WHERE kind = ?" if kind else ""
    params: list = ([kind] if kind else []) + [max(1, min(limit, 200))]
    with connection.get_db() as conn:
        rows = conn.execute(
            f"""SELECT id, kind, title, body, data_json, reported_at, received_at
                FROM bot_reports {where}
                ORDER BY reported_at DESC, id DESC
                LIMIT ?""",
            params,
        ).fetchall()

    return JSONResponse({
        "reports": [
            {
                "id": row["id"],
                "kind": row["kind"],
                "title": row["title"],
                "body": row["body"],
                "data": json.loads(row["data_json"]) if row["data_json"] else None,
                "reported_at": row["reported_at"],
                "received_at": row["received_at"],
            }
            for row in rows
        ],
    })
