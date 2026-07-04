"""한국 주식 수급 데이터 수집 job."""

from __future__ import annotations

import logging

from dashboard.backend.collectors.naver_finance import fetch_investor_deal_trend, fetch_market_volume
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


def upsert_kr_market_volume(kospi_records: list[dict], kosdaq_records: list[dict]) -> int:
    by_date: dict[str, dict] = {}
    for record in kospi_records:
        by_date.setdefault(record["date"], {})["kospi_value"] = record["value"]
    for record in kosdaq_records:
        by_date.setdefault(record["date"], {})["kosdaq_value"] = record["value"]

    with get_db() as conn:
        for row_date, values in by_date.items():
            conn.execute(
                """INSERT INTO kr_market_volume (date, kospi_value, kosdaq_value)
                   VALUES (?, ?, ?)
                   ON CONFLICT(date) DO UPDATE SET
                       kospi_value = COALESCE(excluded.kospi_value, kr_market_volume.kospi_value),
                       kosdaq_value = COALESCE(excluded.kosdaq_value, kr_market_volume.kosdaq_value)""",
                (
                    row_date,
                    values.get("kospi_value"),
                    values.get("kosdaq_value"),
                ),
            )
    return len(by_date)


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_kr_investor_flow() -> None:
    """KOSPI/KOSDAQ 투자자별 수급과 시장 거래대금을 수집해 저장한다."""
    total = 0
    for market in ("KOSPI", "KOSDAQ"):
        records = await fetch_investor_deal_trend(market, days=30)
        if not records:
            raise RuntimeError(f"{market} 투자자 수급 데이터 없음")
        total += upsert_kr_investor_flow(market, records)

    kospi_volume = await fetch_market_volume("KOSPI", days=30)
    kosdaq_volume = await fetch_market_volume("KOSDAQ", days=30)
    if not kospi_volume:
        raise RuntimeError("KOSPI 거래대금 데이터 없음")
    if not kosdaq_volume:
        raise RuntimeError("KOSDAQ 거래대금 데이터 없음")
    volume_total = upsert_kr_market_volume(kospi_volume, kosdaq_volume)

    logger.info("한국 투자자 수급 저장 완료: %d건", total)
    logger.info("한국 시장 거래대금 저장 완료: %d건", volume_total)
