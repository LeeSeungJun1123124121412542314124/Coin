"""대시보드 통합 진입점.

봇의 FastAPI 앱에 대시보드 라우터를 마운트하고,
apscheduler로 스케줄 작업을 내장 실행한다.
프론트엔드 빌드 결과물을 StaticFiles로 서빙한다.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 루트(e:/Dev/coin)와 crypto-volatility-bot 패키지를 Python 경로에 추가
_ROOT = Path(__file__).parents[2]
_BOT_ROOT = _ROOT / "crypto-volatility-bot"
for _p in (str(_ROOT), str(_BOT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bot.webhook_server import create_app
from app.notification_dispatcher import NotificationDispatcher
from app.pipeline import run_analysis
from app.utils.config import Config
from app.utils.logger import setup_logger

from dashboard.backend.db.connection import get_connection

logger = logging.getLogger(__name__)

_FRONTEND_DIST = Path(__file__).parents[1] / "frontend" / "dist"


def _build_app() -> FastAPI:
    config = Config.from_env()
    setup_logger("dashboard", level=config.log_level)
    logger.info("대시보드 서버 시작")

    # DB 초기화 (앱 시작 시 스키마 생성)
    get_connection()

    dispatcher = NotificationDispatcher(config)

    # ── 봇 파이프라인 함수 ──────────────────────────────────────
    async def pipeline_fn():
        results, errors = await run_analysis(config)
        await dispatcher.dispatch_event_alerts(results, errors)
        _save_analysis_history(results)
        return [r for _, r in results]

    async def report_fn():
        results, errors = await run_analysis(config)
        await dispatcher.dispatch_periodic_report(results, errors)

    # ── 봇 앱 생성 후 대시보드 라우터 마운트 ──────────────────
    app = create_app(pipeline_fn=pipeline_fn, report_fn=report_fn)
    _mount_dashboard_routers(app)

    # ── apscheduler 설정 ────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="UTC")
    _register_jobs(scheduler, config, dispatcher)

    @app.on_event("startup")
    async def on_startup():
        scheduler.start()
        logger.info("스케줄러 시작")

    @app.on_event("shutdown")
    async def on_shutdown():
        scheduler.shutdown(wait=False)
        logger.info("스케줄러 종료")

    # ── 프론트엔드 정적 파일 서빙 ──────────────────────────────
    if _FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
        logger.info("프론트엔드 서빙: %s", _FRONTEND_DIST)
    else:
        logger.warning("프론트엔드 빌드 없음 (npm run build 필요): %s", _FRONTEND_DIST)

    return app


def _save_analysis_history(results) -> None:
    """봇 분석 결과를 analysis_history 테이블에 저장."""
    import json
    from dashboard.backend.db.connection import get_db

    with get_db() as conn:
        for symbol, result in results:
            conn.execute(
                """INSERT INTO analysis_history
                   (symbol, final_score, alert_score, alert_level, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    symbol,
                    result.final_score,
                    result.alert_score,
                    result.alert_level,
                    json.dumps(result.details if hasattr(result, "details") else {}),
                ),
            )


def _mount_dashboard_routers(app: FastAPI) -> None:
    """대시보드 API 라우터를 앱에 등록."""
    from dashboard.backend.api.dashboard_routes import router as dashboard_router
    from dashboard.backend.api.spf_routes import router as spf_router
    from dashboard.backend.api.volume_routes import router as volume_router
    from dashboard.backend.api.market_routes import router as market_router
    from dashboard.backend.api.liquidity_routes import router as liquidity_router
    from dashboard.backend.api.cvd_routes import router as cvd_router
    from dashboard.backend.api.whale_routes import router as whale_router
    from dashboard.backend.api.research_routes import router as research_router
    from dashboard.backend.api.visitor_routes import router as visitor_router
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(spf_router, prefix="/api")
    app.include_router(volume_router, prefix="/api")
    app.include_router(market_router, prefix="/api")
    app.include_router(liquidity_router, prefix="/api")
    app.include_router(cvd_router, prefix="/api")
    app.include_router(whale_router, prefix="/api")
    app.include_router(research_router, prefix="/api")
    app.include_router(visitor_router, prefix="/api")


def _register_jobs(scheduler: AsyncIOScheduler, config, dispatcher) -> None:
    """apscheduler 스케줄 작업 등록."""
    from dashboard.backend.jobs.collect_spf import collect_spf
    from dashboard.backend.jobs.collect_volume import collect_volume
    from dashboard.backend.jobs.collect_whales import collect_whales
    from dashboard.backend.jobs.update_predictions import update_predictions

    # SPF 데이터 수집 — 매일 00:10 UTC
    scheduler.add_job(collect_spf, CronTrigger(hour=0, minute=10))

    # SPF 예측 업데이트 — 매일 00:30 UTC
    scheduler.add_job(update_predictions, CronTrigger(hour=0, minute=30))

    # 거래량 수집 — 매일 00:10 UTC (KST 09:10)
    scheduler.add_job(collect_volume, CronTrigger(hour=0, minute=10))

    # 고래 스냅샷 — 2시간마다
    scheduler.add_job(collect_whales, IntervalTrigger(hours=2))

    # 데일리 브리핑 — 매일 00:00 UTC (KST 09:00)
    scheduler.add_job(
        lambda: dispatcher.send_daily_briefing(),
        CronTrigger(hour=0, minute=0),
    )

    # 주간 성적표 — 매주 일요일 12:00 UTC (KST 21:00)
    scheduler.add_job(
        lambda: dispatcher.send_weekly_report(),
        CronTrigger(day_of_week="sun", hour=12, minute=0),
    )


def create_application() -> FastAPI:
    """uvicorn --factory 모드 진입점."""
    return _build_app()


def main() -> None:
    uvicorn.run(
        "dashboard.backend.main:create_application",
        factory=True,
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    main()
