"""api_error 유틸 + 에러 응답 형식 테스트."""
from __future__ import annotations


def test_api_error_returns_json_response():
    from dashboard.backend.utils.errors import api_error

    resp = api_error(404, "NOT_FOUND", "리소스를 찾을 수 없습니다")
    assert resp.status_code == 404


def test_api_error_body_structure():
    from dashboard.backend.utils.errors import api_error
    import json

    resp = api_error(500, "INTERNAL_ERROR", "서버 오류")
    body = json.loads(resp.body)
    assert "error" in body
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "서버 오류"


def test_api_error_different_status_codes():
    from dashboard.backend.utils.errors import api_error

    for code in (400, 401, 403, 404, 500, 503):
        resp = api_error(code, "CODE", "메시지")
        assert resp.status_code == code
