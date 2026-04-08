"""리서치 분석 API 라우터 — 7개 카테고리 자동 분석."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.backend.services.research_analyzer import analyze_all

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/research-analysis")
async def get_research_analysis():
    """7개 카테고리 자동 분석 결과 반환."""
    try:
        result = await analyze_all()
        return JSONResponse(result)
    except Exception as e:
        logger.error("리서치 분석 실패: %s", e, exc_info=True)
        return JSONResponse({"error": "분석 실패"}, status_code=500)
