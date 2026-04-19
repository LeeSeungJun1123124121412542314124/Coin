"""선물 시뮬레이션 엔진 — 청산가 계산, 펀딩비 처리, SL/TP/청산 판정."""

from __future__ import annotations

import logging
from typing import Optional

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)

# ============================================================
# Bybit USDT-M MMR (Maintenance Margin Rate) 테이블
# ============================================================
_BYBIT_MMR: dict[int, float] = {
    1: 0.005,
    2: 0.005,
    3: 0.01,
    5: 0.01,
    10: 0.02,
    20: 0.025,
    25: 0.025,
    50: 0.03,
    64: 0.04,
}


def _get_mmr(leverage: int) -> float:
    """레버리지에 해당하는 MMR 반환.

    테이블에 없는 레버리지는 다음으로 낮은 키의 MMR을 사용한다.
    예) leverage=7 → 키 5의 MMR(0.01) 반환.
    """
    # 테이블에 정확히 있으면 바로 반환
    if leverage in _BYBIT_MMR:
        return _BYBIT_MMR[leverage]

    # 다음으로 낮은 키를 내림차순 탐색
    for key in sorted(_BYBIT_MMR.keys(), reverse=True):
        if key < leverage:
            return _BYBIT_MMR[key]

    # leverage가 테이블 최솟값보다 작으면 가장 낮은 MMR 반환
    return _BYBIT_MMR[min(_BYBIT_MMR.keys())]


# ============================================================
# 1. 청산가 계산
# ============================================================

def calc_liquidation_price(entry: float, leverage: int, direction: str) -> float:
    """Bybit USDT-M 청산가 계산.

    Args:
        entry: 진입 가격
        leverage: 레버리지 (양의 정수)
        direction: 'long' 또는 'short'

    Returns:
        청산 가격 (float)
    """
    mmr = _get_mmr(leverage)
    if direction == "long":
        return entry * (1 - 1 / leverage + mmr)
    elif direction == "short":
        return entry * (1 + 1 / leverage - mmr)
    else:
        raise ValueError(f"direction은 'long' 또는 'short'여야 합니다. 입력값: {direction!r}")


# ============================================================
# 2. 펀딩비 계산
# ============================================================

def calc_funding_fee(quantity: float, entry_price: float, fr: float) -> float:
    """단일 포지션 펀딩비 계산.

    Args:
        quantity: 포지션 수량 (계약 수)
        entry_price: 진입 가격
        fr: 펀딩 레이트 (예: 0.0001 = 0.01%)

    Returns:
        펀딩비 금액 (양수 = 비용 발생)
    """
    return quantity * entry_price * fr


# ============================================================
# 3. 펀딩비 일괄 적용 (비동기)
# ============================================================

async def _fetch_funding_rate(symbol: str) -> float:
    """현재 펀딩 레이트 조회 (플레이스홀더).

    Task 4/5에서 실제 Bybit API 연동으로 교체 예정.
    현재는 경고 로그 후 0.0 반환.
    """
    logger.warning(
        "펀딩 레이트 조회 미구현 — symbol=%s, 0.0 반환 (Task 4/5에서 Bybit API 연동 예정)",
        symbol,
    )
    return 0.0


async def apply_funding_fees(funding_time: str) -> None:
    """활성 선물 포지션에 펀딩비를 일괄 적용한다.

    Args:
        funding_time: 펀딩 적용 시각 (ISO 8601 문자열)

    처리 흐름:
    1. status='pending' 이고 instrument_type='futures' 인 포지션 조회
    2. 심볼별 펀딩 레이트 조회 (플레이스홀더)
    3. 펀딩비 계산 후 sim_funding_events 삽입
    4. sim_positions.funding_fee_accrued 업데이트
    5. sim_accounts.capital 및 updated_at 업데이트
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                sp.id            AS position_id,
                sp.prediction_id,
                sp.quantity,
                sp.leverage,
                sp.funding_fee_accrued,
                pred.entry_price,
                pred.direction,
                pred.asset_symbol,
                pred.account_id
            FROM sim_positions AS sp
            JOIN sim_predictions AS pred ON pred.id = sp.prediction_id
            WHERE pred.status = 'pending'
              AND sp.instrument_type = 'futures'
            """
        ).fetchall()

    if not rows:
        logger.info("apply_funding_fees: 활성 선물 포지션 없음 (funding_time=%s)", funding_time)
        return

    processed = 0
    for row in rows:
        position_id = row["position_id"]
        quantity = row["quantity"]
        entry_price = row["entry_price"]
        direction = row["direction"]
        asset_symbol = row["asset_symbol"]
        account_id = row["account_id"]
        current_accrued = row["funding_fee_accrued"] or 0.0

        # 펀딩 레이트 조회 (플레이스홀더)
        fr = await _fetch_funding_rate(asset_symbol)

        # 펀딩비 계산
        funding_amount = calc_funding_fee(quantity, entry_price, fr)

        # Bybit 컨벤션:
        #   FR > 0 → 롱 지불, 숏 수취
        #   FR < 0 → 롱 수취, 숏 지불
        # capital_delta: 계좌에 더할 금액 (음수면 차감)
        if direction == "long":
            capital_delta = -funding_amount   # 롱은 FR>0일 때 차감
        else:
            capital_delta = funding_amount    # 숏은 FR>0일 때 수취

        with get_db() as conn:
            # 펀딩 이벤트 기록
            conn.execute(
                """
                INSERT INTO sim_funding_events
                    (position_id, funding_time, fr_value, funding_amount)
                VALUES (?, ?, ?, ?)
                """,
                (position_id, funding_time, fr, funding_amount),
            )

            # 포지션 누적 펀딩비 업데이트
            new_accrued = current_accrued + funding_amount
            conn.execute(
                "UPDATE sim_positions SET funding_fee_accrued = ? WHERE id = ?",
                (new_accrued, position_id),
            )

            # 계좌 자본 업데이트
            conn.execute(
                """
                UPDATE sim_accounts
                SET capital = capital + ?, updated_at = ?
                WHERE id = ?
                """,
                (capital_delta, funding_time, account_id),
            )

        processed += 1

    logger.info(
        "apply_funding_fees 완료: %d개 포지션 처리 (funding_time=%s)",
        processed,
        funding_time,
    )


# ============================================================
# 4. SL / TP / 청산 트리거 판정
# ============================================================

async def check_sl_tp_liquidation(position_id: int) -> Optional[str]:
    """포지션의 SL/TP/청산 조건을 최신 1시간봉 기준으로 판정한다.

    판정 우선순위:
    1. 청산가 (liquidated)
    2. 손절가 (stop_loss)
    3. 익절가 (take_profit)

    Args:
        position_id: sim_positions.id

    Returns:
        "liquidated" | "stop_loss" | "take_profit" | None
    """
    with get_db() as conn:
        pos = conn.execute(
            """
            SELECT
                sp.id,
                sp.stop_loss,
                sp.take_profit,
                sp.liquidation_price,
                pred.direction,
                pred.asset_symbol
            FROM sim_positions AS sp
            JOIN sim_predictions AS pred ON pred.id = sp.prediction_id
            WHERE sp.id = ?
            """,
            (position_id,),
        ).fetchone()

        if pos is None:
            logger.warning("check_sl_tp_liquidation: position_id=%d 없음", position_id)
            return None

        direction = pos["direction"]
        asset_symbol = pos["asset_symbol"]
        liq_price = pos["liquidation_price"]
        stop_loss = pos["stop_loss"]
        take_profit = pos["take_profit"]

        # 최신 1시간봉 조회 (timestamp DESC)
        bar = conn.execute(
            """
            SELECT high, low
            FROM coin_ohlcv_1h
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (asset_symbol,),
        ).fetchone()

    if bar is None:
        logger.warning(
            "check_sl_tp_liquidation: %s 의 OHLCV 데이터 없음 — 판정 불가",
            asset_symbol,
        )
        return None

    high = bar["high"]
    low = bar["low"]

    # 1순위: 청산가 체크
    if liq_price is not None:
        if direction == "long" and low <= liq_price:
            return "liquidated"
        if direction == "short" and high >= liq_price:
            return "liquidated"

    # 2순위: 손절가 체크
    if stop_loss is not None:
        if direction == "long" and low <= stop_loss:
            return "stop_loss"
        if direction == "short" and high >= stop_loss:
            return "stop_loss"

    # 3순위: 익절가 체크
    if take_profit is not None:
        if direction == "long" and high >= take_profit:
            return "take_profit"
        if direction == "short" and low <= take_profit:
            return "take_profit"

    return None
