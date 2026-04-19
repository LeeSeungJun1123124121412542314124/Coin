"""대시보드 통합 진입점.

봇의 FastAPI 앱에 대시보드 라우터를 마운트하고,
apscheduler로 스케줄 작업을 내장 실행한다.
프론트엔드 빌드 결과물을 StaticFiles로 서빙한다.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 루트와 crypto-volatility-bot 패키지를 Python 경로에 추가
_ROOT = Path(__file__).parents[2]
_BOT_ROOT = _ROOT / "crypto-volatility-bot"
for _p in (str(_ROOT), str(_BOT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import os

import uvicorn
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.bot.webhook_server import create_app
from app.notification_dispatcher import NotificationDispatcher
from app.pipeline import run_analysis
from app.utils.config import Config
from app.utils.logger import setup_logger

from dashboard.backend.db.connection import get_connection, get_db
from dashboard.backend.utils.errors import api_error
from dashboard.backend.utils.limiter import limiter
from dashboard.backend.utils.retry import async_retry
from dashboard.backend.utils.alerting import notify_job_failure

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

    # ── Rate limiter 설정 ───────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── apscheduler 설정 ────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="UTC")
    _register_jobs(scheduler, config, dispatcher)

    # ── 헬스체크 전용 엔드포인트 ───────────────────────────────
    from fastapi.responses import JSONResponse

    @app.get("/api/health")
    async def health():
        # DB 연결 확인
        db_ok = True
        try:
            with get_db() as conn:
                conn.execute("SELECT 1")
        except Exception:
            db_ok = False

        # 스케줄러 상태
        sched_running = scheduler.running if scheduler else False

        status = "ok" if (db_ok and sched_running) else "degraded"
        return JSONResponse({
            "status": status,
            "db": db_ok,
            "scheduler": sched_running,
        })

    # ── 글로벌 예외 핸들러 ─────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error("미처리 예외: %s", exc, exc_info=True)
        return api_error(500, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다")

    # ── 타임스탬프 미들웨어 ────────────────────────────────────
    class TimestampMiddleware(BaseHTTPMiddleware):
        """모든 JSON 응답에 _timestamp 필드 자동 주입."""
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            ct = response.headers.get("content-type", "")
            if ct.startswith("application/json"):
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                try:
                    data = json.loads(body)
                    if isinstance(data, dict):
                        data["_timestamp"] = datetime.now(timezone.utc).isoformat()
                    body = json.dumps(data, ensure_ascii=False).encode()
                except (json.JSONDecodeError, TypeError):
                    pass
                # content-length 제거 → Response 생성자가 새 body 크기로 재계산
                new_headers = {
                    k: v for k, v in response.headers.items()
                    if k.lower() != "content-length"
                }
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=new_headers,
                    media_type="application/json",
                )
            return response

    app.add_middleware(TimestampMiddleware)

    # ── CORS 미들웨어 ───────────────────────────────────────────
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def on_startup():
        scheduler.start()
        logger.info("스케줄러 시작")
        try:
            from dashboard.backend.jobs.collect_spf import collect_spf

            await collect_spf()
            logger.info("시작 시 SPF 초기 수집 완료")
        except Exception as e:
            logger.error("시작 시 SPF 초기 수집 실패: %s", e, exc_info=True)
        try:
            from dashboard.backend.collectors.bybit_ohlcv import collect_coin_ohlcv_1h

            await collect_coin_ohlcv_1h()
            logger.info("시작 시 1시간봉 초기 수집 완료")
        except Exception as e:
            logger.error("시작 시 1시간봉 초기 수집 실패: %s", e, exc_info=True)

    @app.on_event("shutdown")
    async def on_shutdown():
        scheduler.shutdown(wait=False)
        logger.info("스케줄러 종료")

    # ── 프론트엔드 정적 파일 서빙 ──────────────────────────────
    # StaticFiles(html=True)는 SPA 라우팅을 지원하지 않음 — /volume 같은 React Router
    # 경로를 브라우저가 직접 요청하면 dist/volume 파일이 없어 404를 반환함.
    # catch-all 라우트로 실제 파일은 그대로 서빙하고, 나머지는 index.html 반환.
    if _FRONTEND_DIST.exists():
        from fastapi.responses import FileResponse as _FileResponse

        _index_html = str(_FRONTEND_DIST / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            candidate = _FRONTEND_DIST / full_path
            if candidate.is_file():
                return _FileResponse(str(candidate))
            return _FileResponse(_index_html)

        logger.info("프론트엔드 서빙 (SPA): %s", _FRONTEND_DIST)
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
    """대시보드 API 라우터를 앱에 등록.

    공개 엔드포인트: GET /api/health, POST /api/auth/verify-pin
    인증 필요: 나머지 모든 라우터 (Bearer 토큰)
    """
    from dashboard.backend.api.alert_routes import router as alert_router
    from dashboard.backend.api.auth_routes import router as auth_router
    from dashboard.backend.api.dashboard_routes import router as dashboard_router
    from dashboard.backend.api.spf_routes import router as spf_router
    from dashboard.backend.api.volume_routes import router as volume_router
    from dashboard.backend.api.market_routes import router as market_router
    from dashboard.backend.api.liquidity_routes import router as liquidity_router
    from dashboard.backend.api.cvd_routes import router as cvd_router
    from dashboard.backend.api.whale_routes import router as whale_router
    from dashboard.backend.api.research_routes import router as research_router
    from dashboard.backend.api.visitor_routes import router as visitor_router
    from dashboard.backend.api.coin_slots_routes import router as coin_slots_router
    from dashboard.backend.api.stock_index_routes import router as stock_index_router
    from dashboard.backend.api.stock_slots_routes import router as stock_slots_router
    from dashboard.backend.middleware.auth import require_auth

    # 인증 불필요 — PIN 검증 엔드포인트
    app.include_router(auth_router, prefix="/api")

    # 인증 필요 — Bearer 토큰 검증
    _auth_dep = [Depends(require_auth)]
    app.include_router(dashboard_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(spf_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(volume_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(market_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(liquidity_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(cvd_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(whale_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(research_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(visitor_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(alert_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(coin_slots_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(stock_index_router, prefix="/api", dependencies=_auth_dep)
    app.include_router(stock_slots_router, prefix="/api", dependencies=_auth_dep)


def _register_jobs(scheduler: AsyncIOScheduler, config, dispatcher) -> None:
    """apscheduler 스케줄 작업 등록."""
    from dashboard.backend.jobs.collect_spf import collect_spf
    from dashboard.backend.jobs.collect_volume import collect_volume
    from dashboard.backend.jobs.collect_whales import collect_whales
    from dashboard.backend.jobs.collect_kimchi import collect_kimchi
    from dashboard.backend.jobs.update_predictions import update_predictions
    from dashboard.backend.collectors.bybit_ohlcv import collect_coin_ohlcv_1h

    # SPF 데이터 수집 — 매일 00:10 UTC
    scheduler.add_job(collect_spf, CronTrigger(hour=0, minute=10))

    # SPF 예측 업데이트 — 매일 00:30 UTC
    scheduler.add_job(update_predictions, CronTrigger(hour=0, minute=30))

    # 거래량 수집 — 매일 00:10 UTC (KST 09:10)
    scheduler.add_job(collect_volume, CronTrigger(hour=0, minute=10))

    # 고래 스냅샷 — 2시간마다
    scheduler.add_job(collect_whales, IntervalTrigger(hours=2))

    # 김치 프리미엄 히스토리 — 2시간마다
    scheduler.add_job(collect_kimchi, IntervalTrigger(hours=2))

    # 코인 1시간봉 수집 — 매 시간 1분 (1시간 봉 마감 후)
    scheduler.add_job(collect_coin_ohlcv_1h, CronTrigger(minute=1))

    # 봇 분석 — 매시간 이벤트 알림 (긴급/고래)
    @async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
    async def _hourly_alerts():
        try:
            results, errors = await run_analysis(config)
            await dispatcher.dispatch_event_alerts(results, errors)
            _save_analysis_history(results)
            logger.info("매시간 분석 완료: %d개 종목", len(results))
        except Exception as e:
            logger.error("매시간 분석 실패: %s", e, exc_info=True)
            raise  # 예외 전파 — decorator가 재시도

    scheduler.add_job(_hourly_alerts, IntervalTrigger(hours=1))

    # 봇 리포트 — 12시간마다 전체 리포트 발송
    @async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
    async def _periodic_report():
        try:
            results, errors = await run_analysis(config)
            await dispatcher.dispatch_periodic_report(results, errors)
            logger.info("정기 리포트 발송: %d개 종목", len(results))
        except Exception as e:
            logger.error("정기 리포트 실패: %s", e, exc_info=True)
            raise  # 예외 전파 — decorator가 재시도

    scheduler.add_job(_periodic_report, CronTrigger(hour="0,12", minute=5))


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
