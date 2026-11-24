"""리서치 분석 결과를 날짜별로 저장하는 job — 카드의 어제·7일 전 대비 표시용."""

from __future__ import annotations

import logging

from dashboard.backend.services import research_history
from dashboard.backend.services.research_analyzer import analyze_all
from dashboard.backend.utils.alerting import notify_job_failure
from dashboard.backend.utils.retry import async_retry

logger = logging.getLogger(__name__)


@async_retry(max_retries=2, backoff_base=2.0, on_failure=notify_job_failure)
async def snapshot_research() -> None:
    """현재 분석 결과를 오늘(KST) 행으로 저장한다. 하루에 여러 번 돌아 그날의 마지막 값이 남는다."""
    result = await analyze_all()
    saved = research_history.save_snapshot(result["categories"], research_history.kst_today())
    logger.info("리서치 스냅샷 저장: %d개 항목", saved)
