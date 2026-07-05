"""CBOE Put/Call 비율 수집 job."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from dashboard.backend.collectors.cboe import fetch_putcall
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_putcall(record: dict) -> None:
    updated_at = _utc_now().isoformat()
    for key in ("total_pc", "equity_pc", "index_pc"):
        value = record.get(key)
        if value is not None and not 0.3 <= float(value) <= 2.0:
            logger.warning("CBOE Put/Call 비율 범위 확인 필요: %s=%s", key, value)

    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO cboe_putcall
               (date, total_pc, equity_pc, index_pc, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                record["date"],
                record.get("total_pc"),
                record.get("equity_pc"),
                record.get("index_pc"),
                updated_at,
            ),
        )


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_putcall() -> None:
    record = await fetch_putcall()
    if record is None:
        logger.info("CBOE Put/Call 수집 스킵: 데이터 없음")
        return
    upsert_putcall(record)
    logger.info("CBOE Put/Call 저장: %s", record["date"])
