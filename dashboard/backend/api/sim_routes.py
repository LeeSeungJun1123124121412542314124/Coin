"""시뮬레이터 API 라우터 — 자동 백테스트·튜닝·지표 리더보드."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query
from pydantic import BaseModel, Field

from dashboard.backend.services.auto_backtest import run_backtest
from dashboard.backend.services.backtest_tuner import (
    get_job_path,
    run_walk_forward,
)
from dashboard.backend.services.composite_backtest import (
    CompositeBacktestParams,
    run_composite_backtest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================
# Pydantic 모델
# ============================================================

class CompositeBacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", description="거래 심볼 (예: BTCUSDT)")
    interval: str = Field(default="1h", description="캔들 단위: 1h | 4h | 1d")
    start_date: str = Field(..., description="백테스트 시작일 (YYYY-MM-DD)")
    end_date: str = Field(..., description="백테스트 종료일 (YYYY-MM-DD)")
    stop_loss_pct: float = Field(default=3.0, gt=0, le=50, description="손절 비율 (%)")
    take_profit_pct: float = Field(default=5.0, gt=0, le=100, description="익절 비율 (%)")
    long_threshold: float = Field(default=70.0, ge=1, le=99, description="롱 진입 임계값 (1~99)")
    short_threshold: float = Field(default=70.0, ge=1, le=99, description="숏 진입 임계값 (1~99)")
    leverage: float = Field(default=1.0, ge=1, le=100, description="레버리지 (1~100배)")
    position_size_pct: float = Field(default=100.0, gt=0, le=100, description="포지션 크기 (%)")
    initial_capital: float = Field(default=10000.0, gt=0, description="초기 자본 (USDT)")
    score_exit_buffer: float = Field(default=15.0, ge=0, lt=100, description="score_exit 완충값 — exit 기준 = threshold - buffer")


# ============================================================
# GET /sim/auto-backtest
# ============================================================

@router.get("/sim/auto-backtest")
async def get_auto_backtest(
    symbol: str = Query(default="BTCUSDT"),
    horizon_h: int = Query(default=24),
    lookback: int = Query(default=500),
):
    """자동 백테스트 실행 및 결과 반환."""
    if horizon_h not in (4, 8, 24):
        raise HTTPException(status_code=422, detail="horizon_h must be 4, 8, or 24")
    if not (50 <= lookback <= 1000):
        raise HTTPException(status_code=422, detail="lookback must be between 50 and 1000")
    try:
        return await run_backtest(symbol.strip().upper(), horizon_h, lookback)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.error("자동 백테스트 실패: %s %sh", symbol, horizon_h, exc_info=True)
        raise HTTPException(status_code=500, detail="백테스트 실행 실패")


# ============================================================
# GET /sim/projection
# ============================================================


# ============================================================
# POST /sim/composite-backtest — 종합 자동 백테스트
# ============================================================

@router.post("/sim/composite-backtest")
async def composite_backtest_endpoint(req: CompositeBacktestRequest):
    """매크로 + 기술 지표 복합 점수 기반 자동 트레이딩 시뮬레이션."""
    params = CompositeBacktestParams(
        symbol=req.symbol,
        interval=req.interval,
        start_date=req.start_date,
        end_date=req.end_date,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        long_threshold=req.long_threshold,
        short_threshold=req.short_threshold,
        leverage=req.leverage,
        position_size_pct=req.position_size_pct,
        initial_capital=req.initial_capital,
        score_exit_buffer=req.score_exit_buffer,
    )
    result = await run_composite_backtest(params)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ============================================================
# POST /sim/tune — 자동 튜닝(Walk-forward) 시작
# ============================================================

class TuningRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", description="거래 심볼 (튜닝 자체는 단일 심볼)")
    interval: str = Field(default="1h", description="캔들 단위: 1h | 4h | 1d")
    start_date: str = Field(..., description="튜닝 데이터 시작일 (YYYY-MM-DD)")
    end_date: str = Field(..., description="튜닝 데이터 종료일 (YYYY-MM-DD)")
    initial_capital: float = Field(default=10000.0, gt=0, description="초기 자본 (USDT)")
    n_trials: int = Field(default=200, ge=20, le=1000, description="윈도우당 Optuna trial 수")
    n_windows: int = Field(default=9, ge=3, le=12, description="walk-forward 윈도우 수")


class TuningStartResponse(BaseModel):
    job_id: str
    status: str = "queued"


@router.post("/sim/tune", response_model=TuningStartResponse)
async def start_tuning(req: TuningRequest, background_tasks: BackgroundTasks):
    """자동 튜닝 작업을 비동기로 큐잉하고 job_id를 반환한다.

    실제 실행은 BackgroundTasks가 별 thread에서 호출 (FastAPI는 sync def
    background에 thread pool을 자동 사용).
    """
    job_id = str(uuid.uuid4())

    base_params = CompositeBacktestParams(
        symbol=req.symbol,
        interval=req.interval,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
    )

    background_tasks.add_task(
        run_walk_forward,
        job_id,
        base_params,
        req.n_trials,
        req.n_windows,
    )

    return TuningStartResponse(job_id=job_id, status="queued")


# ============================================================
# GET /sim/tune/{job_id} — 진행률 + 결과 조회
# ============================================================

@router.get("/sim/tune/{job_id}")
async def get_tuning_status(job_id: str = Path(..., description="튜닝 작업 ID")):
    """튜닝 작업 상태를 반환한다 (queued/running/completed/failed)."""
    path = get_job_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"job_id={job_id} 작업을 찾을 수 없습니다")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.exception("튜닝 결과 파일 읽기 실패: %s", path)
        raise HTTPException(status_code=500, detail=f"결과 파일 읽기 실패: {exc}")


# ============================================================
# 지표 리더보드 (포워드 모의투자) — paper_engine
# ============================================================
@router.get("/sim/leaderboard")
async def get_leaderboard():
    """지표별 총수익·승률·MDD·Sharpe·vs매수보유 순위."""
    from dashboard.backend.services.paper_engine import leaderboard
    return {"leaderboard": leaderboard()}


@router.get("/sim/leaderboard/{indicator}")
async def get_leaderboard_detail(indicator: str = Path(..., description="지표명")):
    """특정 지표의 에쿼티 곡선 + 포지션 이력."""
    from dashboard.backend.services.paper_engine import portfolio_detail
    detail = portfolio_detail(indicator)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"포트폴리오 없음: {indicator}")
    return detail


@router.post("/sim/leaderboard/reset")
async def reset_leaderboard(indicator: str | None = Query(default=None, description="없으면 전체 리셋")):
    """시드 리셋 (전체 또는 지표별)."""
    from dashboard.backend.services.paper_engine import reset
    return {"reset": reset(indicator)}
