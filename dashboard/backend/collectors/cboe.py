"""CBOE 일별 Put/Call 비율 수집."""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_DAILY_STATS_URL = "https://www.cboe.com/markets/us/options/market-statistics/daily/"
_LABELS = {
    "total_pc": "TOTAL PUT/CALL RATIO",
    "index_pc": "INDEX PUT/CALL RATIO",
    "equity_pc": "EQUITY PUT/CALL RATIO",
}


def _find_ratio(html: str, label: str) -> float | None:
    text = re.sub(r"<[^>]+>", " ", html)
    match = re.search(rf"{re.escape(label)}\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if match:
        return float(match.group(1))

    compact = html.replace(r"\"", '"')
    match = re.search(
        rf'"name"\s*:\s*"{re.escape(label)}"\s*,\s*"value"\s*:\s*"([0-9]+(?:\.[0-9]+)?)"',
        compact,
        re.I,
    )
    return float(match.group(1)) if match else None


def parse_putcall_html(html: str) -> dict | None:
    """CBOE Daily Market Statistics HTML에서 거래일과 Put/Call 비율 3종을 추출한다."""
    date_match = re.search(r'selectedDate\\?":\\?"(\d{4}-\d{2}-\d{2})', html)
    if not date_match:
        return None

    record: dict[str, float | str] = {"date": date_match.group(1)}
    for key, label in _LABELS.items():
        value = _find_ratio(html, label)
        if value is None:
            return None
        record[key] = value
    return record


async def fetch_putcall() -> dict | None:
    """공식 CBOE 일별 통계 페이지에서 최신 Put/Call 비율을 조회한다.

    404만 휴장(데이터 없음)으로 보고 None을 반환한다. 200인데 파싱이 실패하면
    페이지 구조 변경 의심이므로 예외를 던져 job의 재시도·경보 경로를 태운다.
    """
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(_DAILY_STATS_URL)
        if resp.status_code == 404:
            logger.info("CBOE Put/Call 데이터 없음: 404")
            return None
        resp.raise_for_status()
    record = parse_putcall_html(resp.text)
    if record is None:
        raise ValueError("CBOE Put/Call 파싱 실패 — 페이지 구조 변경 의심")
    return record
