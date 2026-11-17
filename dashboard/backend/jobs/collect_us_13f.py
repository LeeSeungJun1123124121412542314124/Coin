"""미국 기관 13F 보유 수집 job."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
import re

from dashboard.backend.collectors.edgar import (
    fetch_filing_index,
    fetch_infotable,
    fetch_recent_13f_filings,
    fetch_ticker_title_map,
)

from dashboard.backend.db.connection import get_db
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 400
_REQUEST_DELAY_S = 0.15

# 2026-08-23 SEC submissions API의 CIK별 name으로 검증:
# BERKSHIRE HATHAWAY INC, Bridgewater Associates LP,
# CITADEL ADVISORS LLC, RENAISSANCE TECHNOLOGIES LLC.
_INSTITUTIONS = [
    ("Berkshire Hathaway", 1067983),
    ("Bridgewater Associates", 1350694),
    ("Citadel Advisors", 1423053),
    ("Renaissance Technologies", 1037389),
]


def _us_slot_tickers() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT ticker FROM stock_slots WHERE market='us' ORDER BY position"
        ).fetchall()
    return [row["ticker"].upper() for row in rows]


def _institution_matches(institution: str, edgar_name: str) -> bool:
    return institution.casefold() in edgar_name.casefold()


# 회사 형태 접미사 표기 통일 — EDGAR 공식명('Apple Inc.', 'NVIDIA CORP')과
# 13F nameOfIssuer('APPLE INC', 'NVIDIA CORPORATION')가 기관마다 다르게 적힌다
_SUFFIX_ALIASES = {"CORPORATION": "CORP", "INCORPORATED": "INC", "COMPANY": "CO", "LIMITED": "LTD"}


def _issuer_key(name: str) -> str:
    """대소문자·구두점·회사 형태 접미사 표기 차이를 지운 발행사 매칭 키."""
    words = re.sub(r"[^\w\s]", " ", name.upper()).split()
    return " ".join(_SUFFIX_ALIASES.get(word, word) for word in words)


def known_13f_accessions() -> set[str]:
    """이미 처리를 끝낸 13F accession 집합을 반환한다."""
    with get_db() as conn:
        rows = conn.execute("SELECT accession_no FROM us_13f_filings").fetchall()
    return {row["accession_no"] for row in rows}


def upsert_13f_filing(
    accession_no: str,
    cik: int,
    institution: str,
    filed_at: str,
    report_date: str,
) -> None:
    """매칭 결과가 없어도 처리 완료한 filing 메타를 기록한다."""
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO us_13f_filings
               (accession_no, cik, institution, filed_at, report_date, processed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                accession_no,
                cik,
                institution,
                filed_at,
                report_date,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def replace_13f_holdings(
    accession_no: str,
    institution: str,
    cik: int,
    quarter: str,
    holdings: list[dict],
) -> int:
    """동일 기관·분기의 기존 접수를 새 접수 보유 내역으로 교체한다."""
    with get_db() as conn:
        conn.execute("DELETE FROM us_13f_holdings WHERE cik=? AND quarter=?", (cik, quarter))
        conn.executemany(
            """INSERT INTO us_13f_holdings
               (accession_no, seq, institution, cik, ticker, issuer_name,
                quarter, shares, value_usd, put_call)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    accession_no,
                    row["seq"],
                    institution,
                    cik,
                    row["ticker"],
                    row["issuer_name"],
                    quarter,
                    row["shares"],
                    row["value_usd"],
                    row["put_call"],
                )
                for row in holdings
            ],
        )
    return len(holdings)


@async_retry(max_retries=3, on_failure=notify_job_failure)
async def collect_us_13f_holdings() -> None:
    """화이트리스트 기관의 최근 13F에서 us 슬롯 종목 보유를 수집한다."""
    tickers = _us_slot_tickers()
    if not tickers:
        logger.info("us 슬롯 없음 — 13F 수집 스킵")
        return

    title_map = await fetch_ticker_title_map()
    title_to_ticker = {
        _issuer_key(title_map[ticker]): ticker
        for ticker in tickers
        if ticker in title_map
    }
    known = known_13f_accessions()
    since = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    total = 0
    failed: list[str] = []

    for institution, cik in _INSTITUTIONS:
        await asyncio.sleep(_REQUEST_DELAY_S)
        edgar_name, filings = await fetch_recent_13f_filings(cik, since)
        if not _institution_matches(institution, edgar_name):
            logger.warning(
                "13F 기관명 불일치: 설정=%s, EDGAR=%s, CIK=%s — 스킵",
                institution,
                edgar_name,
                cik,
            )
            continue

        for filing in sorted(filings, key=lambda item: item["filed_at"]):
            accession_no = filing["accession_no"]
            if accession_no in known:
                continue
            await asyncio.sleep(_REQUEST_DELAY_S)
            try:
                document = await fetch_filing_index(cik, accession_no)
                await asyncio.sleep(_REQUEST_DELAY_S)
                rows = await fetch_infotable(cik, accession_no, document)
            except Exception as e:
                # 공시 1건 실패가 나머지 공시·기관 수집을 막지 않도록 건너뛰고, 루프 후 예외로 알림
                logger.warning("13F 공시 처리 실패 — 스킵: %s %s: %s", institution, accession_no, e)
                failed.append(f"{accession_no}({e})")
                continue
            holdings = []
            for seq, row in enumerate(rows):
                ticker = title_to_ticker.get(_issuer_key(row["issuer_name"]))
                if ticker is None:
                    logger.warning(
                        "13F issuer 슬롯 매칭 실패: %s (%s)",
                        row["issuer_name"],
                        accession_no,
                    )
                    continue
                holdings.append({"seq": seq, "ticker": ticker, **row})

            total += replace_13f_holdings(
                accession_no,
                institution,
                cik,
                filing["report_date"],
                holdings,
            )
            upsert_13f_filing(
                accession_no,
                cik,
                institution,
                filing["filed_at"],
                filing["report_date"],
            )
            known.add(accession_no)

    logger.info("미국 기관 13F 보유 저장 완료: %d건", total)
    if failed:
        raise RuntimeError(f"13F 공시 {len(failed)}건 처리 실패: {', '.join(failed)}")
