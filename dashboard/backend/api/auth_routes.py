"""PIN 인증 API — 서버 측 PIN 검증 후 토큰 발급."""
from __future__ import annotations
import hmac

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.backend.middleware.auth import PIN_CODE, create_token

router = APIRouter()


class PinRequest(BaseModel):
    pin: str


@router.post("/auth/verify-pin")
async def verify_pin(body: PinRequest) -> JSONResponse:
    """PIN 검증 후 Bearer 토큰 발급."""
    if not hmac.compare_digest(body.pin, PIN_CODE):
        return JSONResponse(
            {"error": {"code": "INVALID_PIN", "message": "잘못된 PIN입니다"}},
            status_code=401,
        )
    token = create_token({"type": "user"})
    return JSONResponse({"token": token})
