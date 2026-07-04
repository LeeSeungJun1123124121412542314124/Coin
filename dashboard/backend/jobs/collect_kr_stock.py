"""한국 주식 수급 데이터 수집 job."""

from __future__ import annotations

import logging

from dashboard.backend.collectors.naver_finance import fetch_investor_deal_trend
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)


def upsert_kr_investor_flow(market: str, records: list[dict]) -> int:
    with get_db() as conn:
        for record in records:
            conn.execute(
                """INSERT INTO kr_investor_flow
                   (date, market, foreign_net, institution_net, individual_net)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(date, market) DO UPDATE SET
                       foreign_net = excluded.foreign_net,
                       institution_net = excluded.institution_net,
                       individual_net = excluded.individual_net""",
                (
                    record["date"],
                    market,
                    record["foreign_net"],
                    record["institution_net"],
                    record["individual_net"],
                ),
            )
    return len(records)


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_kr_investor_flow() -> None:
    """KOSPI/KOSDAQ 투자자별 수급을 수집해 저장한다."""
    total = 0
    for market in ("KOSPI", "KOSDAQ"):
        records = await fetch_investor_deal_trend(market, days=30)
        if not records:
            raise RuntimeError(f"{market} 투자자 수급 데이터 없음")
        total += upsert_kr_investor_flow(market, records)

    logger.info("한국 투자자 수급 저장 완료: %d건", total)
