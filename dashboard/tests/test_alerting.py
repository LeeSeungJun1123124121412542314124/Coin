"""잡 실패 알림 — 텔레그램 HTML 파싱 실패로 알림이 조용히 사라지는 버그 회귀 테스트."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from dashboard.backend.utils import alerting


def _patch_client(monkeypatch, status_code: int, body: dict) -> list[dict]:
    """alerting의 httpx.AsyncClient를 실제 네트워크 없는 MockTransport로 교체, 전송 payload 수집."""
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(status_code, json=body)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        alerting.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(alerting, "_TELEGRAM_TOKEN", "test-token")
    monkeypatch.setattr(alerting, "_CHAT_ID", "test-chat")
    return sent


@pytest.mark.asyncio
async def test_error_text_is_html_escaped(monkeypatch) -> None:
    # 실제 파이썬 예외 문자열 — 텔레그램이 "Unsupported start tag"로 400 거부하던 케이스
    sent = _patch_client(monkeypatch, 200, {"ok": True})

    await alerting.notify_job_failure(
        "collect_spf", "'<' not supported between instances of 'NoneType' and 'float' & more"
    )

    text = sent[0]["text"]
    assert "&lt;" in text and "&amp;" in text
    assert "'<'" not in text
    assert text.startswith("⚠️ <b>잡 실패</b>")  # 의도한 서식 태그는 유지


@pytest.mark.asyncio
async def test_telegram_rejection_is_logged(monkeypatch, caplog) -> None:
    # 텔레그램 4xx 응답은 httpx가 예외를 던지지 않아 로그 없이 사라졌다
    _patch_client(
        monkeypatch, 400, {"ok": False, "description": "Bad Request: can't parse entities"}
    )

    with caplog.at_level(logging.ERROR, logger=alerting.logger.name):
        await alerting.notify_job_failure("collect_spf", "boom")

    messages = [r.getMessage() for r in caplog.records]
    assert any("잡 실패 알림 발송 실패" in m for m in messages)
    assert all("test-token" not in m for m in messages)  # 요청 URL의 봇 토큰이 로그로 새지 않아야 함
