"""HMAC 기반 간단 인증 미들웨어."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException, Request

# 환경변수에서 설정 로드
PIN_CODE = os.getenv("PIN_CODE", "1234")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
APP_SECRET = os.getenv("APP_SECRET", "change-me-in-production")

# 토큰 유효기간: 24시간
_TOKEN_TTL = 86400


def create_token(data: dict) -> str:
    """HMAC-SHA256 서명 토큰 생성."""
    payload = json.dumps({**data, "exp": int(time.time()) + _TOKEN_TTL})
    sig = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def verify_token(token: str) -> bool:
    """토큰 유효성 검증 (서명 + 만료시간 확인)."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit("|", 1)
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        # 타이밍 어택 방지를 위해 compare_digest 사용
        if not hmac.compare_digest(sig, expected):
            return False
        data = json.loads(payload)
        return data.get("exp", 0) > time.time()
    except Exception:
        return False


async def require_auth(request: Request) -> None:
    """일반 사용자 인증 — Bearer 토큰 검증."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")


async def require_admin(request: Request) -> None:
    """관리자 인증 — X-Admin-Key 헤더 검증."""
    key = request.headers.get("X-Admin-Key", "")
    if not ADMIN_KEY or not hmac.compare_digest(key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="관리자 권한이 필요합니다")
