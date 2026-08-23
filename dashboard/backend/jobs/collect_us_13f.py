"""미국 기관 13F 보유 수집 job."""

from __future__ import annotations

from datetime import datetime, timezone

from dashboard.backend.db.connection import get_db


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
