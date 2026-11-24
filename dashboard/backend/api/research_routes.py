"""리서치 분석 API 라우터 — 7개 카테고리 자동 분석."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.services.research_analyzer import analyze_all
from dashboard.backend.services.research_history import attach_comparisons, kst_today
from dashboard.backend.utils.errors import api_error

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/research-analysis")
async def get_research_analysis():
    """7개 카테고리 자동 분석 결과 반환."""
    try:
        result = await analyze_all()
        try:
            # 어제·7일 전 저장분을 붙인다 — 실패해도 분석 결과는 그대로 내보낸다
            result = attach_comparisons(result, kst_today())
        except Exception as e:
            logger.warning("리서치 비교값 조회 실패(비교 없이 응답): %s", e)
        return JSONResponse(result)
    except Exception as e:
        logger.error("리서치 분석 실패: %s", e, exc_info=True)
        return api_error(500, "RESEARCH_ERROR", "분석 실패")
