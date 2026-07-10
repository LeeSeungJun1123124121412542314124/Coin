"""Dashboard 테스트 공통 픽스처."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 테스트용 환경변수 — 모듈 임포트 전에 설정해야 module-level 상수에 반영됨
os.environ.setdefault("PIN_CODE", "1234")
os.environ.setdefault("APP_SECRET", "test-secret-key")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")

# 텔레그램 자격 선점 차단 — main.py 임포트 시 load_dotenv(override=False)가
# .env의 실제 토큰을 로드해, 잡 실패 경로 테스트가 진짜 알림을 발송하는 사고 방지
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

# app.macro 임포트 경로 — 런타임 main.py가 crypto-volatility-bot을 sys.path에 넣는 것과 동일
_BOT_DIR = str(Path(__file__).resolve().parents[2] / "crypto-volatility-bot")
if _BOT_DIR not in sys.path:
    sys.path.insert(0, _BOT_DIR)


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
