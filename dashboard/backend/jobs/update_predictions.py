"""SPF 예측 결과 업데이트 — 매일 00:30 UTC.

3일 전 예측의 실제 BTC 가격 변화를 확인하여 hit/miss를 판정한다.
spf_records의 price_after_3d/7d/14d도 함께 업데이트한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)


@async_retry(max_retries=3, backoff_base=2.0)
async def update_predictions() -> None:
    """3/7/14일 전 레코드의 사후 가격 및 예측 결과 업데이트."""
    logger.info("예측 결과 업데이트 시작")

    btc_today = await _get_btc_price()
    if btc_today is None:
        logger.warning("BTC 가격 없음, 업데이트 건너뜀")
        return

    today = date.today()

    with get_db() as conn:
        # 3일 전 레코드 업데이트
        _update_after_price(conn, today - timedelta(days=3), btc_today, "price_after_3d")
        # 7일 전
        _update_after_price(conn, today - timedelta(days=7), btc_today, "price_after_7d")
        # 14일 전
        _update_after_price(conn, today - timedelta(days=14), btc_today, "price_after_14d")

        # 3일 전 예측 hit/miss 판정
        _judge_prediction(conn, today - timedelta(days=3), btc_today)

    logger.info("예측 결과 업데이트 완료")


def _update_after_price(conn, target_date: date, current_price: float, col: str) -> None:
    """특정 날짜 레코드의 사후 가격 컬럼 업데이트."""
    conn.execute(
        f"UPDATE spf_records SET {col} = ? WHERE date = ? AND {col} IS NULL",
        (current_price, target_date.isoformat()),
    )


def _judge_prediction(conn, target_date: date, btc_today: float) -> None:
    """예측 결과 판정.

    예측일 BTC 가격 대비 3일 후(오늘) 가격으로 hit/miss 결정.
    """
    row = conn.execute(
        """SELECT p.date, p.direction, s.price as price_then
           FROM predictions p
           JOIN spf_records s ON s.date = p.date
           WHERE p.date = ? AND p.result IS NULL""",
        (target_date.isoformat(),),
    ).fetchone()

    if not row:
        return

    price_then = row["price_then"]
    if not price_then:
        return

    change_pct = (btc_today - price_then) / price_then * 100
    direction = row["direction"]

    if direction == "상승" and change_pct > 1.0:
        result = "hit"
    elif direction == "하락" and change_pct < -1.0:
        result = "hit"
    elif direction == "중립" and abs(change_pct) <= 2.0:
        result = "hit"
    else:
        result = "miss"

    conn.execute(
        "UPDATE predictions SET result = ?, actual_price_3d = ? WHERE date = ?",
        (result, btc_today, target_date.isoformat()),
    )
    logger.info("예측 판정 %s: %s → %s (가격변화 %.2f%%)", target_date, direction, result, change_pct)


async def _get_btc_price() -> float | None:
    from app.data.data_collector import DataCollector

    loop = asyncio.get_running_loop()
    try:
        collector = DataCollector()
        ohlcv = await loop.run_in_executor(None, collector.fetch_ohlcv, "BTC/USDT", "1d", 1)
        if ohlcv is not None and len(ohlcv) > 0:
            return float(ohlcv["close"].iloc[-1])
    except Exception as e:
        logger.error("BTC 가격 조회 실패: %s", e)
    return None
