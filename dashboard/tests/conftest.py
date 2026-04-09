"""Dashboard 테스트 공통 픽스처."""
from __future__ import annotations

import os
import pytest

# 테스트용 환경변수 — 모듈 임포트 전에 설정해야 module-level 상수에 반영됨
os.environ.setdefault("PIN_CODE", "1234")
os.environ.setdefault("APP_SECRET", "test-secret-key")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")


@pytest.fixture
def auth_client():
    """인증 라우터만 포함한 최소 FastAPI TestClient."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dashboard.backend.api.auth_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def valid_token():
    """유효한 JWT 토큰 반환."""
    from dashboard.backend.middleware.auth import create_token
    return create_token({"type": "user"})
