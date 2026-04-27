"""만료된 시뮬레이션 예측 자동 채점 — 매 시간 5분 (UTC).

처리 흐름:
1. status='pending' AND expiry_time <= now 인 예측 조회
2. 마켓별 만료 시점 실제 가격 조회 (crypto / kr_stock / us_stock)
3. 채점 지표 계산 후 sim_settlements 삽입
4. sim_predictions.status 업데이트 ('settled' 또는 'liquidated')
5. 포트폴리오 모드: sim_accounts.capital += pnl
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)


# ============================================================
# 가격 조회 헬퍼
# ============================================================

async def _get_crypto_price(symbol: str) -> Optional[float]:
    """coin_ohlcv_1h 테이블에서 가장 최근 close 반환."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT close FROM coin_ohlcv_1h WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    if row is None:
        return None
    return float(row["close"])


async def _get_kr_stock_price(symbol: str) -> Optional[float]:
    """네이버 파이낸스에서 한국 주식 최근 일봉 close 반환."""
    from dashboard.backend.collectors.naver_finance import fetch_naver_ohlcv

    bars = await fetch_naver_ohlcv(symbol, "1d")
    if not bars:
        return None
    return float(bars[-1]["close"])


async def _get_us_stock_price(symbol: str) -> Optional[float]:
    """Yahoo Finance에서 미국 주식 최근 일봉 close 반환."""
    from dashboard.backend.collectors.yahoo_finance import fetch_stock_ohlcv

    bars = await fetch_stock_ohlcv(symbol, "1d")
    if not bars:
        return None
    return float(bars[-1]["close"])


async def _get_actual_price(market: str, symbol: str) -> Optional[float]:
    """마켓 유형에 따라 적절한 가격 조회 함수 호출."""
    if market == "crypto":
        return await _get_crypto_price(symbol)
    elif market == "kr_stock":
        return await _get_kr_stock_price(symbol)
    elif market == "us_stock":
        return await _get_us_stock_price(symbol)
    else:
        logger.warning("알 수 없는 마켓 유형: %s", market)
        return None


# ============================================================
# 채점 계산
# ============================================================

def _calc_direction_hit(direction: Optional[str], actual: float, entry: float) -> Optional[int]:
    """방향 적중 여부 반환.

    Returns:
        1 (적중) / 0 (미적중) / None (방향 없음)
    """
    if direction is None:
        return None
    if direction == "long":
        return 1 if actual > entry else 0
    if direction == "short":
        return 1 if actual < entry else 0
    return None


def _calc_price_error(actual: float, target: Optional[float]) -> Optional[float]:
    """MAE (목표가 대비 절대 오차)."""
    if target is None:
        return None
    return abs(actual - target)


def _calc_pnl(
    actual: float,
    entry: float,
    direction: Optional[str],
    quantity: Optional[float],
    leverage: Optional[int],
    mode: str,
) -> tuple[Optional[float], Optional[float]]:
    """PnL 및 PnL% 계산.

    Returns:
        (pnl, pnl_pct) — 포트폴리오 모드이고 포지션 정보가 있을 때만 계산.
        그 외에는 (None, None).
    """
    if mode != "portfolio" or quantity is None or entry == 0:
        return None, None

    direction_sign = 1 if direction == "long" else -1
    pnl = (actual - entry) * quantity * direction_sign

    # 선물: 레버리지 적용
    if leverage and leverage > 1:
        pnl *= leverage

    pnl_pct = pnl / (entry * quantity) * 100
    return pnl, pnl_pct


# ============================================================
# 메인 배치 함수
# ============================================================

async def settle_expired_predictions() -> None:
    """만료된 pending 예측을 일괄 채점하고 결과를 DB에 저장한다."""
    now_iso = datetime.now(timezone.utc).isoformat()
    logger.info("settle_expired_predictions 시작 (기준 시각: %s)", now_iso)

    # 1. 만료된 pending 예측 조회 (sim_accounts join)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id            AS pred_id,
                p.account_id,
                p.asset_symbol,
                p.mode,
                p.direction,
                p.target_price,
                p.entry_price,
                p.expiry_time,
                a.market
            FROM sim_predictions AS p
            JOIN sim_accounts AS a ON a.id = p.account_id
            WHERE p.status = 'pending'
              AND p.expiry_time <= ?
            """,
            (now_iso,),
        ).fetchall()

    if not rows:
        logger.info("채점 대상 예측 없음")
        return

    logger.info("채점 대상: %d개 예측", len(rows))

    settled_count = 0

    for row in rows:
        pred_id    = row["pred_id"]
        account_id = row["account_id"]
        symbol     = row["asset_symbol"]
        mode       = row["mode"]
        direction  = row["direction"]
        target_price = row["target_price"]
        entry_price  = float(row["entry_price"]) if row["entry_price"] is not None else None
        market     = row["market"]

        try:
            # 2-a. 실제 가격 조회
            actual_price = await _get_actual_price(market, symbol)
            if actual_price is None:
                logger.warning(
                    "pred_id=%d: %s (%s) 가격 조회 실패 — 건너뜀",
                    pred_id, symbol, market,
                )
                continue

            # 2-c. 포지션 정보 조회 (포트폴리오 모드)
            position = None
            if mode == "portfolio":
                with get_db() as conn:
                    position = conn.execute(
                        """
                        SELECT id, quantity, leverage, instrument_type, liquidation_price
                        FROM sim_positions
                        WHERE prediction_id = ?
                        LIMIT 1
                        """,
                        (pred_id,),
                    ).fetchone()

            # Fix I-5: 포트폴리오 모드인데 포지션이 없으면 건너뜀
            if mode == "portfolio" and position is None:
                logger.warning("포트폴리오 예측 %s: sim_positions 없음, 채점 건너뜀", pred_id)
                continue

            quantity       = float(position["quantity"])   if position and position["quantity"]   is not None else None
            leverage       = int(position["leverage"])     if position and position["leverage"]   is not None else None
            liq_price_db   = float(position["liquidation_price"]) if position and position["liquidation_price"] is not None else None
            # Fix C-1: 첫 번째 SELECT에 id 포함 후 중복 쿼리 제거
            position_id    = position["id"] if position else None

            # 2-c. SL/TP/청산 판정
            liquidated = 0
            # Fix I-6: crypto 마켓이고 position_id 있을 때만 SL/TP/청산 판정
            if market == "crypto" and position_id is not None:
                from dashboard.backend.services.sim_engine import check_sl_tp_liquidation

                trigger = await check_sl_tp_liquidation(position_id)
                if trigger == "liquidated":
                    liquidated = 1
                    # 청산가를 실제 가격으로 사용
                    if liq_price_db is not None:
                        actual_price = liq_price_db
            else:
                trigger = None

            # 채점 지표 계산
            # Fix C-3: entry_price is not None 명시적 체크
            direction_hit = _calc_direction_hit(direction, actual_price, entry_price) if entry_price is not None else None
            price_error   = _calc_price_error(actual_price, target_price)
            # Fix C-2: entry_price None 명시적 처리
            if entry_price is None and mode == "portfolio":
                logger.warning("포트폴리오 예측 %s: entry_price 없음, 채점 건너뜀", pred_id)
                continue
            pnl, pnl_pct  = _calc_pnl(
                actual_price, entry_price,
                direction, quantity, leverage, mode,
            )
            # mdd, sharpe: 플레이스홀더 (향후 구현)
            mdd    = None
            sharpe = None

            settled_at = now_iso
            final_status = "liquidated" if liquidated else "settled"

            # 2-d. sim_settlements 삽입
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO sim_settlements
                        (prediction_id, settled_at, actual_price, direction_hit,
                         price_error, pnl, pnl_pct, mdd, sharpe, liquidated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pred_id, settled_at, actual_price, direction_hit,
                        price_error, pnl, pnl_pct, mdd, sharpe, liquidated,
                    ),
                )

                # 2-e. sim_predictions.status 업데이트
                conn.execute(
                    "UPDATE sim_predictions SET status = ? WHERE id = ?",
                    (final_status, pred_id),
                )

                # 2-f. 포트폴리오 모드: 계좌 자본 반영
                if mode == "portfolio" and pnl is not None:
                    conn.execute(
                        "UPDATE sim_accounts SET capital = capital + ?, updated_at = ? WHERE id = ?",
                        (pnl, settled_at, account_id),
                    )

            logger.info(
                "pred_id=%d 채점 완료: status=%s actual=%.4f direction_hit=%s pnl=%s",
                pred_id, final_status, actual_price, direction_hit, pnl,
            )
            settled_count += 1

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pred_id=%d 채점 중 오류 — 건너뜀: %s", pred_id, exc, exc_info=True
            )

    # 3. 처리 결과 로그
    logger.info(
        "settle_expired_predictions 완료: %d / %d 건 채점",
        settled_count, len(rows),
    )
