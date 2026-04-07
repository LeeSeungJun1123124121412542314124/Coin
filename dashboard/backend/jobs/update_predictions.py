"""SPF 예측 결과 업데이트 — 매일 00:30 UTC.

3일 전 예측의 실제 결과(hit/miss)를 판정하여 predictions 테이블 업데이트.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def update_predictions() -> None:
    """3일 전 예측 결과 판정 (Phase 2에서 구현)."""
    logger.info("예측 결과 업데이트 시작")
    # TODO: Phase 2 — 실제 BTC 가격과 예측 비교 후 hit/miss 기록
