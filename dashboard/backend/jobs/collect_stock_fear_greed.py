"""미국 주식 Fear & Greed 지수 수집 job."""

from __future__ import annotations

import logging

from dashboard.backend.collectors.cnn_fear_greed import fetch_fear_greed
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)


def upsert_stock_fear_greed(record: dict) -> int:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO stock_fear_greed (date, value, rating, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   value = excluded.value,
                   rating = excluded.rating,
                   updated_at = excluded.updated_at""",
            (
                record["date"],
                record["value"],
                record.get("rating"),
                record["updated_at"],
            ),
        )
    return 1


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_stock_fear_greed() -> None:
    record = await fetch_fear_greed()
    if not record:
        raise RuntimeError("CNN Fear & Greed 데이터 없음")
    upsert_stock_fear_greed(record)
    logger.info("미국 주식 Fear & Greed 저장 완료: %s", record["date"])
