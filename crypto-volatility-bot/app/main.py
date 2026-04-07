"""FastAPI server entry point for the Crypto Volatility Analysis Bot."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from app.bot.webhook_server import create_app
from app.notification_dispatcher import NotificationDispatcher
from app.pipeline import run_analysis
from app.utils.config import Config
from app.utils.logger import setup_logger


def _build_app() -> FastAPI:
    config = Config.from_env()
    logger = setup_logger("crypto-bot", level=config.log_level)
    logger.info("Bot started", extra={"symbols": config.symbols})

    dispatcher = NotificationDispatcher(config)

    async def pipeline_fn():
        """Hourly: analysis + event alerts only (emergency/whale)."""
        results, errors = await run_analysis(config)
        await dispatcher.dispatch_event_alerts(results, errors)
        return [r for _, r in results]

    async def report_fn():
        """Every 12 hours: analysis + periodic report + event alerts."""
        results, errors = await run_analysis(config)
        await dispatcher.dispatch_periodic_report(results, errors)

    return create_app(pipeline_fn=pipeline_fn, report_fn=report_fn)


def create_application() -> FastAPI:
    """uvicorn --factory 모드 진입점."""
    return _build_app()


def main() -> None:
    uvicorn.run(
        "app.main:create_application",
        factory=True,
        host="0.0.0.0",
        port=8080,
    )


if __name__ == "__main__":
    main()
