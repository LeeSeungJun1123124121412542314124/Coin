"""FastAPI webhook server — Telegram webhook + scheduler trigger + health check."""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Telegram webhook 보안 토큰 (설정된 경우에만 검증)
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

def _check_admin(request: Request) -> JSONResponse | None:
    """관리자 키 검증 — ADMIN_KEY 미설정 시 검증 생략, 실패 시 403 반환."""
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        return None  # 개발/테스트 환경: 키 미설정 시 허용
    key = request.headers.get("X-Admin-Key", "")
    if not hmac.compare_digest(key, admin_key):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return None


def create_app(
    pipeline_fn: Callable[[], Coroutine[Any, Any, list]] | None = None,
    report_fn: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> FastAPI:
    app = FastAPI(title="crypto-volatility-bot")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.post("/webhook")
    async def webhook(request: Request) -> JSONResponse:
        # secret_token 검증 (환경변수 설정된 경우에만)
        if WEBHOOK_SECRET:
            token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if token != WEBHOOK_SECRET:
                return JSONResponse({"error": "Forbidden"}, status_code=403)

        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        update_id = body.get("update_id")
        if update_id is None:
            raise HTTPException(status_code=400, detail="Missing update_id")

        message = body.get("message", {})
        text = message.get("text", "")
        logger.info("Received webhook update %s: %s", update_id, text)
        return JSONResponse({"ok": True})

    @app.post("/scheduled-run")
    async def scheduled_run(request: Request) -> JSONResponse:
        # 관리자 키 검증
        if (err := _check_admin(request)) is not None:
            return err
        if pipeline_fn is not None:
            try:
                results = await pipeline_fn()
                return JSONResponse({"ok": True, "count": len(results)})
            except Exception as e:
                logger.error("Scheduled run failed: %s", e)
                return JSONResponse({"ok": False, "error": "Internal server error"}, status_code=500)
        return JSONResponse({"ok": True, "count": 0})

    @app.post("/scheduled-report")
    async def scheduled_report(request: Request) -> JSONResponse:
        """12시간 주기 리포트 — 관리자 전용."""
        # 관리자 키 검증
        if (err := _check_admin(request)) is not None:
            return err
        if report_fn is not None:
            try:
                await report_fn()
                return JSONResponse({"ok": True})
            except Exception as e:
                logger.error("Scheduled report failed: %s", e)
                return JSONResponse({"ok": False, "error": "Internal server error"}, status_code=500)
        return JSONResponse({"ok": True})

    return app
