"""고래 스냅샷 수집 — 2시간마다.

Hyperliquid 리더보드 TOP 10 + 포지션을 수집하여 whale_snapshots 테이블에 저장.
"""

from __future__ import annotations

import json
import logging

from dashboard.backend.utils.retry import async_retry
from dashboard.backend.collectors.hyperliquid import fetch_top_whale_positions
from dashboard.backend.db.connection import get_db

logger = logging.getLogger(__name__)


@async_retry(max_retries=3, backoff_base=2.0)
async def collect_whales() -> None:
    """HL 고래 스냅샷 수집 및 DB 저장."""
    logger.info("고래 스냅샷 수집 시작")

    try:
        whales = await fetch_top_whale_positions(top_n=10)
    except Exception as e:
        logger.error("고래 데이터 조회 실패: %s", e)
        return

    if not whales:
        logger.warning("고래 데이터 없음, 저장 건너뜀")
        return

    with get_db() as conn:
        for whale in whales:
            positions_json = json.dumps(whale.get("positions", []))
            conn.execute(
                """INSERT INTO whale_snapshots
                   (address, nickname, account_value, pnl, roi, positions)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    whale.get("address", ""),
                    whale.get("display_name"),
                    whale.get("account_value"),
                    whale.get("pnl_30d"),
                    whale.get("roi_30d"),
                    positions_json,
                ),
            )

    logger.info("고래 스냅샷 저장 완료: %d명", len(whales))
