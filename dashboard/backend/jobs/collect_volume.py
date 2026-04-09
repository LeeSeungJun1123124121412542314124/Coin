"""거래량 수집 — 매일 00:10 UTC (KST 09:10, KRX 마감 후).

업비트/빗썸 24h 거래대금을 수집하여 volume_daily 테이블에 저장.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from dashboard.backend.utils.retry import async_retry
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.collectors.upbit import fetch_krw_volume as upbit_volume
from dashboard.backend.collectors.bithumb import fetch_krw_volume as bithumb_volume
from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)


@async_retry(max_retries=3, backoff_base=2.0, on_failure=notify_job_failure)
async def collect_volume() -> None:
    """거래소 거래량 수집."""
    logger.info("거래량 수집 시작")

    today = date.today().isoformat()

    upbit_krw, bithumb_krw = await asyncio.gather(
        upbit_volume(),
        bithumb_volume(),
        return_exceptions=True,
    )

    if isinstance(upbit_krw, Exception):
        logger.error("업비트 거래량 실패: %s", upbit_krw)
        upbit_krw = None
    if isinstance(bithumb_krw, Exception):
        logger.error("빗썸 거래량 실패: %s", bithumb_krw)
        bithumb_krw = None

    if upbit_krw is None and bithumb_krw is None:
        logger.warning("모든 거래량 수집 실패, 저장 건너뜀")
        return

    # 크립토/주식 비율 계산 (업비트+빗썸 합산 기준)
    total_crypto = (upbit_krw or 0) + (bithumb_krw or 0)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO volume_daily (date, upbit_krw, bithumb_krw, crypto_ratio)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   upbit_krw = excluded.upbit_krw,
                   bithumb_krw = excluded.bithumb_krw,
                   crypto_ratio = excluded.crypto_ratio""",
            (today, upbit_krw, bithumb_krw, round(total_crypto, 4)),
        )

    logger.info(
        "거래량 저장 완료: 업비트=%.2f조, 빗썸=%.2f조",
        upbit_krw or 0,
        bithumb_krw or 0,
    )
