"""리서치 API 라우터 — 탭 4.

글 목록 조회, 단건 조회 + 조회수 증가.
관리자 글쓰기는 POST /api/research (Admin-Key 헤더 필요).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


class PostCreate(BaseModel):
    badge: str = ""
    title: str
    subtitle: str = ""
    category: str = ""
    content: str
    read_time: int = 5


@router.get("/research")
async def list_research(limit: int = 20, offset: int = 0):
    """리서치 글 목록 (최신 순)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, badge, title, subtitle, category,
                      views, read_time, published_at
               FROM research_posts
               ORDER BY published_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM research_posts").fetchone()[0]

    return JSONResponse({
        "posts": [dict(r) for r in rows],
        "total": total,
    })


@router.get("/research/{post_id}")
async def get_research(post_id: int):
    """리서치 글 단건 조회 + 조회수 +1."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM research_posts WHERE id = ?", (post_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")

        # 조회수 증가
        conn.execute(
            "UPDATE research_posts SET views = views + 1 WHERE id = ?",
            (post_id,),
        )

    return JSONResponse(dict(row))


@router.post("/research")
async def create_research(
    post: PostCreate,
    admin_key: str = Header(default="", alias="Admin-Key"),
):
    """리서치 글 작성 (Admin-Key 헤더 필요)."""
    if not _ADMIN_KEY or admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="권한 없음")

    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO research_posts
               (badge, title, subtitle, category, content, read_time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (post.badge, post.title, post.subtitle,
             post.category, post.content, post.read_time),
        )
        post_id = cursor.lastrowid

    return JSONResponse({"id": post_id, "ok": True})


@router.delete("/research/{post_id}")
async def delete_research(
    post_id: int,
    admin_key: str = Header(default="", alias="Admin-Key"),
):
    """리서치 글 삭제 (Admin-Key 헤더 필요)."""
    if not _ADMIN_KEY or admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="권한 없음")

    with get_db() as conn:
        conn.execute("DELETE FROM research_posts WHERE id = ?", (post_id,))

    return JSONResponse({"ok": True})
