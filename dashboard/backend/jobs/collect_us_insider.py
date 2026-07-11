"""미국 관심종목 내부자 매매 수집 job (SEC EDGAR Form 4)."""

from __future__ import annotations

import asyncio
import logging

from dashboard.backend.collectors.edgar import (
    fetch_cik_map,
    fetch_form4,
    fetch_recent_form4_filings,
)
from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 90       # 수집·표시 창 (첫 실행 백필 겸용)
_REQUEST_DELAY_S = 0.15   # SEC rate limit (10 req/s) 준수


def _us_slot_tickers() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT ticker FROM stock_slots WHERE market='us' ORDER BY position"
        ).fetchall()
    return [row["ticker"].upper() for row in rows]


def _known_accessions(ticker: str) -> set[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT accession_no FROM us_insider_trades WHERE ticker=?",
            (ticker,),
        ).fetchall()
    return {row["accession_no"] for row in rows}


def upsert_us_insider_trades(ticker: str, accession_no: str, filed_at: str, parsed: dict) -> int:
    with get_db() as conn:
        for seq, tx in enumerate(parsed["transactions"]):
            conn.execute(
                """INSERT OR IGNORE INTO us_insider_trades
                   (accession_no, seq, ticker, filed_at, transaction_date,
                    insider_name, insider_title, code, shares, price, value)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    accession_no,
                    seq,
                    ticker,
                    filed_at,
                    tx["date"],
                    parsed["insider_name"],
                    parsed["insider_title"],
                    tx["code"],
                    tx["shares"],
                    tx["price"],
                    tx["value"],
                ),
            )
    return len(parsed["transactions"])


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_us_insider_trades() -> None:
    """us 슬롯 종목들의 최근 Form 4를 수집해 저장한다. 저장된 accession은 스킵(멱등)."""
    from datetime import date, timedelta

    tickers = _us_slot_tickers()
    if not tickers:
        logger.info("us 슬롯 없음 — 내부자 수집 스킵")
        return

    since = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    cik_map = await fetch_cik_map()

    total = 0
    for ticker in tickers:
        cik = cik_map.get(ticker)
        if cik is None:
            # ETF 등 EDGAR 미등록 심볼은 정상 케이스 — 경보 없이 스킵
            logger.warning("EDGAR CIK 없음: %s — 스킵", ticker)
            continue

        await asyncio.sleep(_REQUEST_DELAY_S)
        filings = await fetch_recent_form4_filings(cik, since)
        known = _known_accessions(ticker)
        for filing in filings:
            if filing["accession_no"] in known:
                continue
            await asyncio.sleep(_REQUEST_DELAY_S)
            parsed = await fetch_form4(cik, filing["accession_no"], filing["primary_document"])
            total += upsert_us_insider_trades(
                ticker, filing["accession_no"], filing["filed_at"], parsed
            )

    logger.info("미국 내부자 매매 저장 완료: %d건", total)
