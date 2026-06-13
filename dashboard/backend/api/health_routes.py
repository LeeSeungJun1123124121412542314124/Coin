"""GET /api/macro-health — 매크로/9팩터 데이터 헬스 (복합 산출 신뢰성 모니터)."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/macro-health")
async def get_macro_health():
    """매크로 캐시 신선도 + 소스별 최신성 + 복합 산출 가능 여부."""
    try:
        from dashboard.backend.services.macro_health import macro_health
        return JSONResponse(macro_health())
    except Exception as e:
        logger.error("매크로 헬스 조회 실패: %s", e)
        return JSONResponse({"status": "no_data", "cache_age_hours": None, "composite": None, "series": [], "message": str(e)})
