"""시뮬레이터 API 라우터 — 계좌, 예측, 포지션, 성과 스코어카드."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from dashboard.backend.db.connection import get_db
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

        # 포트폴리오 모드: 포지션 삽입
        if body.mode == "portfolio":
            conn.execute(
                """
                INSERT INTO sim_positions
                    (prediction_id, instrument_type, quantity, leverage,
                     stop_loss, take_profit, liquidation_price, funding_fee_accrued)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0.0)
                """,
                (
                    prediction_id,
                    body.instrument_type,
                    body.quantity,
                    body.leverage if body.leverage else 1,
                    body.stop_loss,
                    body.take_profit,
                    liquidation_price,
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
