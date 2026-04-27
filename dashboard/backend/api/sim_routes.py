"""시뮬레이터 API 라우터 — 계좌, 예측, 포지션, 성과 스코어카드."""

from __future__ import annotations

import json
import logging
from asyncio import gather
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from dashboard.backend.collectors.bybit_derivatives import fetch_funding_rate, fetch_oi_change
from dashboard.backend.collectors.fred import calc_m2_yoy, calc_tga_yoy, fetch_m2, fetch_tga
from dashboard.backend.db.connection import get_db
from dashboard.backend.services.auto_backtest import run_backtest
from dashboard.backend.services.composite_backtest import (
    CompositeBacktestParams,
    run_composite_backtest,
)
from dashboard.backend.services.return_projector import get_projection
from dashboard.backend.services.signal_analyzer import get_current_signals
from dashboard.backend.services.sim_engine import calc_liquidation_price
from dashboard.backend.services.sim_scorecard import get_scorecard, get_scorecard_by_indicator

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================
# 유효 시장 목록
# ============================================================
_VALID_MARKETS = ("crypto", "kr_stock", "us_stock")


# ============================================================
# Pydantic 모델
# ============================================================

class ResetRequest(BaseModel):
    new_capital: float = Field(..., gt=0)


class PredictionCreate(BaseModel):
    market: Literal["crypto", "kr_stock", "us_stock"]
    asset_symbol: str  # 예: "BTCUSDT", "005930.KS", "AAPL"
    mode: Literal["direction", "target_price", "portfolio"]
    direction: Optional[str] = None  # 'long' 또는 'short'
    target_price: Optional[float] = None
    entry_price: float
    entry_time: str  # ISO 8601
    expiry_time: str  # ISO 8601
    indicator_tags: list[str] = []  # 예: ["OI", "FR"]
    note: Optional[str] = None
    # 포트폴리오/선물 필드 (선택)
    instrument_type: Optional[str] = None  # 'spot' 또는 'futures'
    quantity: Optional[float] = None
    leverage: Optional[int] = Field(default=1, ge=1, le=64)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @field_validator('entry_time', 'expiry_time')
    @classmethod
    def validate_iso_datetime(cls, v):
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError('ISO 8601 형식이어야 합니다 (예: 2026-04-19T12:00:00+00:00)')
        return v


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
# GET /sim/accounts
# ============================================================

@router.get("/sim/accounts")
async def get_sim_accounts():
    """3개 시뮬레이터 계좌 목록 반환 (ROI 포함)."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, market, currency, capital, initial_capital, reset_count,
                   created_at, updated_at
            FROM sim_accounts
            ORDER BY id
            """
        ).fetchall()

    result = []
    for r in rows:
        capital = r["capital"]
        initial = r["initial_capital"]
        roi = (capital - initial) / initial * 100 if initial else 0.0
        result.append({
            "id": r["id"],
            "market": r["market"],
            "currency": r["currency"],
            "capital": capital,
            "initial_capital": initial,
            "reset_count": r["reset_count"],
            "roi": round(roi, 4),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })

    return result


# ============================================================
# POST /sim/accounts/{market}/reset
# ============================================================

@router.post("/sim/accounts/{market}/reset")
async def reset_sim_account(
    body: ResetRequest,
    market: str = Path(...),
):
    """계좌 자본을 리셋하고 reset_count를 1 증가시킨다."""
    if market not in _VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"market은 {_VALID_MARKETS} 중 하나여야 합니다.")

    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        # 현재 계좌 조회
        row = conn.execute(
            "SELECT id, capital FROM sim_accounts WHERE market = ?",
            (market,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail=f"market={market} 계좌를 찾을 수 없습니다.")

        account_id = row["id"]
        capital_before = row["capital"]

        # 리셋 이력 저장
        conn.execute(
            """
            INSERT INTO sim_account_resets (account_id, capital_before, new_capital, reset_at)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, capital_before, body.new_capital, now),
        )

        # 계좌 업데이트 (initial_capital도 갱신해 ROI가 0%로 리셋되도록)
        conn.execute(
            """
            UPDATE sim_accounts
            SET capital = ?, initial_capital = ?, reset_count = reset_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (body.new_capital, body.new_capital, now, account_id),
        )

        # 업데이트된 계좌 반환
        updated = conn.execute(
            """
            SELECT id, market, currency, capital, initial_capital, reset_count,
                   created_at, updated_at
            FROM sim_accounts
            WHERE id = ?
            """,
            (account_id,),
        ).fetchone()

    capital = updated["capital"]
    initial = updated["initial_capital"]
    roi = (capital - initial) / initial * 100 if initial else 0.0

    return {
        "id": updated["id"],
        "market": updated["market"],
        "currency": updated["currency"],
        "capital": capital,
        "initial_capital": initial,
        "reset_count": updated["reset_count"],
        "roi": round(roi, 4),
        "created_at": updated["created_at"],
        "updated_at": updated["updated_at"],
    }


# ============================================================
# GET /sim/predictions
# ============================================================

@router.get("/sim/predictions")
async def get_sim_predictions(
    market: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
):
    """예측 목록 조회 (계좌 + 포지션 LEFT JOIN)."""
    if market and market not in _VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"market은 {_VALID_MARKETS} 중 하나여야 합니다.")
    if status and status not in ("pending", "settled", "liquidated", "cancelled"):
        raise HTTPException(status_code=400, detail="status 값이 올바르지 않습니다.")

    conditions = []
    params: list = []

    if market:
        conditions.append("a.market = ?")
        params.append(market)
    if status:
        conditions.append("p.status = ?")
        params.append(status)
    if asset:
        conditions.append("p.asset_symbol LIKE ?")
        params.append(f"%{asset}%")

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    query = f"""
        SELECT
            p.id, p.account_id, p.asset_symbol, p.mode, p.direction,
            p.target_price, p.entry_price, p.entry_time, p.expiry_time,
            p.status, p.indicator_tags, p.note, p.created_at,
            a.market, a.currency,
            pos.id AS position_id,
            pos.instrument_type, pos.quantity, pos.leverage,
            pos.stop_loss, pos.take_profit, pos.liquidation_price,
            pos.funding_fee_accrued
        FROM sim_predictions AS p
        JOIN sim_accounts AS a ON a.id = p.account_id
        LEFT JOIN sim_positions AS pos ON pos.prediction_id = p.id
        {where_clause}
        ORDER BY p.created_at DESC
        LIMIT 100
    """

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        tags_raw = r["indicator_tags"]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        item = {
            "id": r["id"],
            "account_id": r["account_id"],
            "market": r["market"],
            "currency": r["currency"],
            "asset_symbol": r["asset_symbol"],
            "mode": r["mode"],
            "direction": r["direction"],
            "target_price": r["target_price"],
            "entry_price": r["entry_price"],
            "entry_time": r["entry_time"],
            "expiry_time": r["expiry_time"],
            "status": r["status"],
            "indicator_tags": tags,
            "note": r["note"],
            "created_at": r["created_at"],
        }

        # 포지션 정보 (LEFT JOIN이므로 없을 수 있음)
        if r["position_id"] is not None:
            item["position"] = {
                "id": r["position_id"],
                "instrument_type": r["instrument_type"],
                "quantity": r["quantity"],
                "leverage": r["leverage"],
                "stop_loss": r["stop_loss"],
                "take_profit": r["take_profit"],
                "liquidation_price": r["liquidation_price"],
                "funding_fee_accrued": r["funding_fee_accrued"],
            }
        else:
            item["position"] = None

        result.append(item)

    return result


# ============================================================
# POST /sim/predictions
# ============================================================

@router.post("/sim/predictions")
async def create_sim_prediction(body: PredictionCreate):
    """예측 생성 (포트폴리오 모드는 포지션도 함께 생성)."""
    # 심볼 정규화 (공백 제거 + 대문자)
    asset_symbol = body.asset_symbol.strip().upper()

    # 유효성 검사
    if body.mode == "direction" and not body.direction:
        raise HTTPException(status_code=400, detail="mode='direction'이면 direction 필드가 필요합니다.")
    if body.mode == "target_price" and body.target_price is None:
        raise HTTPException(status_code=400, detail="mode='target_price'이면 target_price 필드가 필요합니다.")
    if body.mode == "portfolio":
        if not body.direction:
            raise HTTPException(status_code=400, detail="mode='portfolio'이면 direction 필드가 필요합니다.")
        if body.quantity is None:
            raise HTTPException(status_code=400, detail="mode='portfolio'이면 quantity 필드가 필요합니다.")
        if not body.instrument_type:
            raise HTTPException(status_code=400, detail="mode='portfolio'이면 instrument_type 필드가 필요합니다.")

    if body.direction and body.direction not in ("long", "short"):
        raise HTTPException(status_code=400, detail="direction은 'long' 또는 'short'여야 합니다.")
    if body.instrument_type and body.instrument_type not in ("spot", "futures"):
        raise HTTPException(status_code=400, detail="instrument_type은 'spot' 또는 'futures'여야 합니다.")

    # 청산가 계산 (선물 포지션)
    liquidation_price: Optional[float] = None
    if body.instrument_type == "futures" and body.direction and body.leverage:
        liquidation_price = calc_liquidation_price(
            entry=body.entry_price,
            leverage=body.leverage,
            direction=body.direction,
        )

    tags_json = json.dumps(body.indicator_tags, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()

    # 포트폴리오 모드: 신호/매크로/예측 사전 수집 (DB 블록 진입 전에 async 처리)
    signal_data = None
    macro_data = None
    projection_data = None
    if body.mode == "portfolio":
        try:
            signal_data = await get_current_signals(asset_symbol)
        except Exception:
            logger.warning("신호 분석 수집 실패 (포지션 생성은 계속)", exc_info=True)

        try:
            direction_str = body.direction or "long"
            lev = body.leverage or 1
            projection_data = await get_projection(asset_symbol, direction_str, lev)
        except Exception:
            logger.warning("수익 예측 수집 실패 (포지션 생성은 계속)", exc_info=True)

        try:
            # 심볼이 USDT 쌍이면 그대로, 아니면 BTCUSDT로 폴백
            derivatives_symbol = asset_symbol if "USDT" in asset_symbol else "BTCUSDT"
            oi_data, fr_data, tga_raw, m2_raw = await gather(
                fetch_oi_change(derivatives_symbol),
                fetch_funding_rate(derivatives_symbol),
                fetch_tga(),
                fetch_m2(),
            )
            macro_data = {
                "oi": oi_data,
                "fr": fr_data,
                "tga_yoy": calc_tga_yoy(tga_raw)[-1] if tga_raw else None,
                "m2_yoy": calc_m2_yoy(m2_raw)[-1] if m2_raw else None,
            }
        except Exception:
            logger.warning("매크로 수집 실패 (포지션 생성은 계속)", exc_info=True)
            macro_data = None

    with get_db() as conn:
        # 계좌 조회
        account_row = conn.execute(
            "SELECT id FROM sim_accounts WHERE market = ?",
            (body.market,),
        ).fetchone()
        if account_row is None:
            raise HTTPException(status_code=404, detail=f"market={body.market} 계좌를 찾을 수 없습니다.")

        account_id = account_row["id"]

        # 예측 삽입
        cursor = conn.execute(
            """
            INSERT INTO sim_predictions
                (account_id, asset_symbol, mode, direction, target_price,
                 entry_price, entry_time, expiry_time, status, indicator_tags, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                account_id,
                asset_symbol,
                body.mode,
                body.direction,
                body.target_price,
                body.entry_price,
                body.entry_time,
                body.expiry_time,
                tags_json,
                body.note,
                now,
            ),
        )
        prediction_id = cursor.lastrowid

        # 포트폴리오 모드: 포지션 삽입 (신호/매크로/예측 포함)
        if body.mode == "portfolio":
            # 신호 데이터 추출
            signal_score_val = signal_data["score"] if signal_data else None
            signal_snapshot_val = (
                json.dumps(signal_data["indicators"], ensure_ascii=False) if signal_data else None
            )
            macro_snapshot_val = (
                json.dumps(macro_data, ensure_ascii=False) if macro_data else None
            )

            # 예측 수익률 추출
            pred_1d = pred_1w = pred_1m = pred_3m = None
            if projection_data and projection_data.get("horizons"):
                for h in projection_data["horizons"]:
                    if h["period"] == "1d":
                        pred_1d = h["base_pct"]
                    elif h["period"] == "1w":
                        pred_1w = h["base_pct"]
                    elif h["period"] == "1m":
                        pred_1m = h["base_pct"]
                    elif h["period"] == "3m":
                        pred_3m = h["base_pct"]

            conn.execute(
                """
                INSERT INTO sim_positions
                    (prediction_id, instrument_type, quantity, leverage,
                     stop_loss, take_profit, liquidation_price, funding_fee_accrued,
                     signal_score, signal_snapshot, macro_snapshot,
                     predicted_1d, predicted_1w, predicted_1m, predicted_3m)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction_id,
                    body.instrument_type,
                    body.quantity,
                    body.leverage if body.leverage else 1,
                    body.stop_loss,
                    body.take_profit,
                    liquidation_price,
                    signal_score_val,
                    signal_snapshot_val,
                    macro_snapshot_val,
                    pred_1d,
                    pred_1w,
                    pred_1m,
                    pred_3m,
                ),
            )

    return JSONResponse(
        status_code=201,
        content={"id": prediction_id, "status": "pending"},
    )


# ============================================================
# DELETE /sim/predictions/{id}
# ============================================================

@router.delete("/sim/predictions/{prediction_id}")
async def cancel_sim_prediction(prediction_id: int = Path(...)):
    """pending 상태의 예측만 취소 처리."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, status FROM sim_predictions WHERE id = ?",
            (prediction_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail=f"예측 id={prediction_id}을 찾을 수 없습니다.")

        if row["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"pending 상태만 취소 가능합니다. 현재 status={row['status']}",
            )

        conn.execute(
            "UPDATE sim_predictions SET status = 'cancelled' WHERE id = ?",
            (prediction_id,),
        )

    return {"id": prediction_id, "status": "cancelled"}


# ============================================================
# GET /sim/scorecard
# ============================================================

@router.get("/sim/scorecard")
async def get_sim_scorecard(
    market: Optional[str] = Query(default=None),
    horizon_days: Optional[int] = Query(default=None, ge=1),
):
    """전체 성과 스코어카드 집계."""
    if market and market not in _VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"market은 {_VALID_MARKETS} 중 하나여야 합니다.")
    return get_scorecard(market=market, horizon_days=horizon_days)


# ============================================================
# GET /sim/scorecard/by-indicator
# ============================================================

@router.get("/sim/scorecard/by-indicator")
async def get_sim_scorecard_by_indicator(
    market: Optional[str] = Query(default=None),
    horizon_days: Optional[int] = Query(default=None, ge=1),
):
    """인디케이터 태그별 성과 집계."""
    if market and market not in _VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"market은 {_VALID_MARKETS} 중 하나여야 합니다.")
    return get_scorecard_by_indicator(market=market, horizon_days=horizon_days)


# ============================================================
# GET /sim/positions/{id}
# ============================================================

@router.get("/sim/positions/{position_id}")
async def get_sim_position(position_id: int = Path(...)):
    """포지션 상세 조회 (연결된 예측 정보 포함)."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                pos.id AS position_id,
                pos.prediction_id,
                pos.instrument_type,
                pos.quantity,
                pos.leverage,
                pos.stop_loss,
                pos.take_profit,
                pos.liquidation_price,
                pos.funding_fee_accrued,
                p.account_id,
                p.asset_symbol,
                p.mode,
                p.direction,
                p.target_price,
                p.entry_price,
                p.entry_time,
                p.expiry_time,
                p.status,
                p.indicator_tags,
                p.note,
                p.created_at,
                a.market,
                a.currency
            FROM sim_positions AS pos
            JOIN sim_predictions AS p ON p.id = pos.prediction_id
            JOIN sim_accounts AS a ON a.id = p.account_id
            WHERE pos.id = ?
            """,
            (position_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"포지션 id={position_id}을 찾을 수 없습니다.")

    tags_raw = row["indicator_tags"]
    try:
        tags = json.loads(tags_raw) if tags_raw else []
    except (json.JSONDecodeError, TypeError):
        tags = []

    return {
        "id": row["position_id"],
        "prediction_id": row["prediction_id"],
        "instrument_type": row["instrument_type"],
        "quantity": row["quantity"],
        "leverage": row["leverage"],
        "stop_loss": row["stop_loss"],
        "take_profit": row["take_profit"],
        "liquidation_price": row["liquidation_price"],
        "funding_fee_accrued": row["funding_fee_accrued"],
        "prediction": {
            "id": row["prediction_id"],
            "account_id": row["account_id"],
            "market": row["market"],
            "currency": row["currency"],
            "asset_symbol": row["asset_symbol"],
            "mode": row["mode"],
            "direction": row["direction"],
            "target_price": row["target_price"],
            "entry_price": row["entry_price"],
            "entry_time": row["entry_time"],
            "expiry_time": row["expiry_time"],
            "status": row["status"],
            "indicator_tags": tags,
            "note": row["note"],
            "created_at": row["created_at"],
        },
    }


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

@router.get("/sim/projection")
async def get_sim_projection(
    symbol: str = Query(default="BTCUSDT"),
    direction: str = Query(default="long"),
    leverage: int = Query(default=1, ge=1, le=64),
):
    """수익 예측 (1d/1w/1m/3m 기간별 예상 범위)."""
    symbol = symbol.strip().upper()
    if direction not in ("long", "short"):
        raise HTTPException(status_code=400, detail="direction은 'long' 또는 'short'여야 합니다.")
    try:
        result = await get_projection(symbol, direction, leverage)
    except Exception:
        logger.error("수익 예측 실패: %s", symbol, exc_info=True)
        raise HTTPException(status_code=500, detail="수익 예측 중 오류 발생")
    if result is None:
        raise HTTPException(status_code=404, detail=f"{symbol} OHLCV 데이터가 부족합니다")
    return result


# ============================================================
# GET /sim/signals
# ============================================================

@router.get("/sim/signals")
async def get_sim_signals(symbol: str = Query(default="BTCUSDT")):
    """실시간 TA 신호 분석."""
    symbol = symbol.strip().upper()
    try:
        result = await get_current_signals(symbol)
    except Exception:
        logger.error("신호 분석 실패: %s", symbol, exc_info=True)
        raise HTTPException(status_code=500, detail="신호 분석 중 오류 발생")
    if result is None:
        raise HTTPException(status_code=404, detail=f"{symbol} 데이터가 부족합니다 (최소 80봉 필요)")
    return result


# ============================================================
# GET /sim/macro-context
# ============================================================

@router.get("/sim/macro-context")
async def get_macro_context():
    """거시 지표 컨텍스트 반환 — OI, FR, TGA YoY, M2 YoY."""

    oi_data, fr_data, tga_raw, m2_raw = await gather(
        fetch_oi_change("BTCUSDT"),
        fetch_funding_rate("BTCUSDT"),
        fetch_tga(),
        fetch_m2(),
    )

    # OI 처리
    oi_result: dict | None = None
    if oi_data is not None:
        change_24h = oi_data.get("change_24h_pct", 0.0)
        if change_24h > 5:
            oi_signal = "caution"
        elif change_24h < -5:
            oi_signal = "easing"
        else:
            oi_signal = "neutral"
        oi_result = {
            "value": oi_data.get("current_oi"),
            "change_24h_pct": change_24h,
            "signal": oi_signal,
        }

    # FR 처리
    fr_result: dict | None = None
    if fr_data is not None:
        fr_value = fr_data.get("funding_rate", 0.0)
        # annualized_pct = 펀딩비 × 3회/일 × 365일 × 100(%)
        annualized_pct = fr_value * 3 * 365 * 100
        if fr_value > 0.0001:
            fr_signal = "long_bias"
        elif fr_value < -0.0001:
            fr_signal = "short_bias"
        else:
            fr_signal = "neutral"
        fr_result = {
            "value": fr_value,
            "annualized_pct": round(annualized_pct, 4),
            "signal": fr_signal,
        }

    # TGA YoY 처리
    tga_result: dict | None = None
    if tga_raw:
        tga_yoy_data = calc_tga_yoy(tga_raw)
        if tga_yoy_data:
            latest_tga = tga_yoy_data[-1]
            tga_pct = latest_tga.get("yoy_pct", 0.0)
            if tga_pct < -10:
                tga_signal = "easing"
            elif tga_pct > 10:
                tga_signal = "tightening"
            else:
                tga_signal = "neutral"
            tga_result = {
                "pct": tga_pct,
                "signal": tga_signal,
            }

    # M2 YoY 처리
    m2_result: dict | None = None
    if m2_raw:
        m2_yoy_data = calc_m2_yoy(m2_raw)
        if m2_yoy_data:
            latest_m2 = m2_yoy_data[-1]
            m2_pct = latest_m2.get("yoy_pct", 0.0)
            if m2_pct > 5:
                m2_signal = "expanding"
            elif m2_pct < 0:
                m2_signal = "contracting"
            else:
                m2_signal = "neutral"
            m2_result = {
                "pct": m2_pct,
                "signal": m2_signal,
            }

    return {
        "oi": oi_result,
        "fr": fr_result,
        "tga_yoy": tga_result,
        "m2_yoy": m2_result,
    }


# ============================================================
# GET /sim/win-rate-analysis
# ============================================================

# 지표별 파라미터 튜닝 제안 (승률 poor 시 노출)
_TUNING_SUGGESTIONS: dict[str, str] = {
    "RSI":     "기간 14→21로 장기화 또는 임계값 30/70→25/75",
    "MACD":    "fast 12→8 (민감도↑) 또는 slow 26→34 (노이즈↓)",
    "BB":      "σ 2.0→2.5로 조정 권장 (신호 필터 강화)",
    "스토캐스틱":  "임계값 20/80→15/85 (과매도/과매수 강화)",
    "ADX":     "강도 기준 25→30 (더 강한 추세만 신호)",
}


@router.get("/sim/win-rate-analysis")
async def get_win_rate_analysis(
    symbol: Optional[str] = Query(default=None),
    market: Optional[str] = Query(default=None),
):
    """지표별 승률 분석 및 파라미터 튜닝 제안."""
    # 심볼 정규화 (None 또는 'ALL' → 전체 조회)
    normalized_symbol = None
    if symbol and symbol.strip().upper() not in ("", "ALL"):
        normalized_symbol = symbol.strip().upper()

    display_symbol = normalized_symbol or "ALL"

    # SQL 쿼리 구성 (심볼 필터 유무 분기)
    if normalized_symbol:
        query = """
            SELECT
                p.direction,
                p.status,
                pos.signal_score,
                pos.signal_snapshot
            FROM sim_predictions p
            JOIN sim_positions pos ON pos.prediction_id = p.id
            WHERE p.status = 'settled'
              AND p.asset_symbol = ?
              AND pos.signal_snapshot IS NOT NULL
            LIMIT 500
        """
        params: list = [normalized_symbol]
    else:
        query = """
            SELECT
                p.direction,
                p.status,
                pos.signal_score,
                pos.signal_snapshot
            FROM sim_predictions p
            JOIN sim_positions pos ON pos.prediction_id = p.id
            WHERE p.status = 'settled'
              AND pos.signal_snapshot IS NOT NULL
            LIMIT 500
        """
        params = []

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    # 데이터가 없으면 빈 응답 반환
    if not rows:
        return {
            "symbol": display_symbol,
            "overall_win_rate": None,
            "total_trades": 0,
            "winning_trades": 0,
            "indicators": [],
        }

    # 전체 승률 집계
    # 승리 판정: direction == 'long' and signal_score > 0  OR  direction == 'short' and signal_score < 0
    total_trades = 0
    winning_trades = 0

    # 지표별 집계 {name: {"wins": int, "total": int}}
    indicator_stats: dict[str, dict[str, int]] = {}

    for row in rows:
        direction = row["direction"]
        signal_score = row["signal_score"]
        snapshot_raw = row["signal_snapshot"]

        if direction is None:
            continue

        total_trades += 1

        # 전체 승패 판정
        is_win = False
        if signal_score is not None:
            if direction == "long" and signal_score > 0:
                is_win = True
            elif direction == "short" and signal_score < 0:
                is_win = True
        if is_win:
            winning_trades += 1

        # 지표별 신호 파싱
        if not snapshot_raw:
            continue
        try:
            indicators_list = json.loads(snapshot_raw)
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(indicators_list, list):
            continue

        for ind in indicators_list:
            if not isinstance(ind, dict):
                continue
            name = ind.get("name")
            signal = ind.get("signal")
            if not name or not signal:
                continue

            # neutral 신호는 집계에서 제외
            if signal == "neutral":
                continue

            # 지표 신호와 포지션 방향 일치 여부 확인
            if name not in indicator_stats:
                indicator_stats[name] = {"wins": 0, "total": 0}

            indicator_stats[name]["total"] += 1
            if signal == direction:  # 예: signal='long', direction='long' → 일치
                indicator_stats[name]["wins"] += 1

    # 전체 승률 계산
    overall_win_rate = (winning_trades / total_trades) if total_trades > 0 else None

    # 지표별 결과 구성
    indicators_result = []
    for name, stats in sorted(indicator_stats.items()):
        total_signals = stats["total"]
        wins = stats["wins"]
        ind_win_rate = wins / total_signals if total_signals > 0 else 0.0

        # 상태 판정
        if ind_win_rate >= 0.60:
            status = "good"
        elif ind_win_rate >= 0.50:
            status = "warning"
        else:
            status = "poor"

        # 튜닝 제안 (poor 상태만)
        suggestion = _TUNING_SUGGESTIONS.get(name) if status == "poor" else None

        indicators_result.append({
            "name": name,
            "win_rate": round(ind_win_rate, 4),
            "total_signals": total_signals,
            "status": status,
            "suggestion": suggestion,
        })

    return {
        "symbol": display_symbol,
        "overall_win_rate": round(overall_win_rate, 4) if overall_win_rate is not None else None,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "indicators": indicators_result,
    }


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
