"""FastAPI webhook server — Telegram webhook + scheduler trigger + health check."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


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
    async def scheduled_run() -> JSONResponse:
        if pipeline_fn is not None:
            try:
                results = await pipeline_fn()
                return JSONResponse({"ok": True, "count": len(results)})
            except Exception as e:
                logger.error("Scheduled run failed: %s", e)
                return JSONResponse({"ok": False, "error": "Internal server error"}, status_code=500)
        return JSONResponse({"ok": True, "count": 0})

    @app.post("/scheduled-report")
    async def scheduled_report() -> JSONResponse:
        """12-hour periodic report — separate from hourly analysis."""
        if report_fn is not None:
            try:
                await report_fn()
                return JSONResponse({"ok": True})
            except Exception as e:
                logger.error("Scheduled report failed: %s", e)
                return JSONResponse({"ok": False, "error": "Internal server error"}, status_code=500)
        return JSONResponse({"ok": True})

    return app
