# dashboard/backend/utils/errors.py
"""통일된 API 에러 응답 유틸."""
from fastapi.responses import JSONResponse


def api_error(status_code: int, code: str, message: str) -> JSONResponse:
    """표준 에러 응답 반환."""
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
    )
