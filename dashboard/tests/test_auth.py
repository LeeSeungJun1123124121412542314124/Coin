"""PIN 인증 API 통합 테스트."""
from __future__ import annotations


class TestVerifyPin:
    def test_correct_pin_returns_token(self, auth_client):
        resp = auth_client.post("/api/auth/verify-pin", json={"pin": "1234"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 10

    def test_wrong_pin_returns_401(self, auth_client):
        resp = auth_client.post("/api/auth/verify-pin", json={"pin": "0000"})
        assert resp.status_code == 401
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_PIN"

    def test_empty_pin_returns_401(self, auth_client):
        resp = auth_client.post("/api/auth/verify-pin", json={"pin": ""})
        assert resp.status_code == 401

    def test_missing_pin_field_returns_422(self, auth_client):
        resp = auth_client.post("/api/auth/verify-pin", json={})
        assert resp.status_code == 422


class TestTokenVerification:
    def test_valid_token_passes_require_auth(self, valid_token):
        from dashboard.backend.middleware.auth import verify_token
        assert verify_token(valid_token) is True

    def test_invalid_token_fails_require_auth(self):
        from dashboard.backend.middleware.auth import verify_token
        assert verify_token("not-a-valid-token") is False

    def test_tampered_token_fails(self, valid_token):
        from dashboard.backend.middleware.auth import verify_token
        # 토큰 마지막 문자 변경 → 서명 불일치
        tampered = valid_token[:-1] + ("A" if valid_token[-1] != "A" else "B")
        assert verify_token(tampered) is False
