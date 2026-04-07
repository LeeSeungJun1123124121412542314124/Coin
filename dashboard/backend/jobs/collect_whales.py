"""고래 스냅샷 수집 — 2시간마다.

Hyperliquid 리더보드 + 포지션을 수집하여 whale_snapshots 테이블에 저장.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def collect_whales() -> None:
    """HL 고래 스냅샷 수집 (Phase 4에서 구현)."""
    logger.info("고래 스냅샷 수집 시작")
    # TODO: Phase 4 — hyperliquid collector 연동
