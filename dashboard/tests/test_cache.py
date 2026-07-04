"""cache 데코레이터 — 빈/실패 결과 캐싱 방지 테스트.

버그: 빈 리스트([])는 None이 아니라 캐싱돼, 일시적 fetch 실패가 24시간 박힘.
"""
from __future__ import annotations

import pytest

from dashboard.backend import cache


@pytest.fixture(autouse=True)
def _clear_store():
    cache._store.clear()
    yield
    cache._store.clear()


@pytest.mark.asyncio
async def test_empty_result_not_cached():
    """빈 리스트 반환 시 캐싱하지 않고 다음 호출에서 재시도한다."""
    calls = {"n": 0}

    @cache.cached(ttl=3600, key_prefix="test_empty")
    async def flaky():
        calls["n"] += 1
        # 1회차: 실패로 빈 리스트, 2회차: 정상 데이터
        return [] if calls["n"] == 1 else [{"v": 1}]

    first = await flaky()
    second = await flaky()
    assert first == []            # 실패는 그대로 반환
    assert second == [{"v": 1}]   # 캐시 오염 없이 재시도해 정상값 획득
    assert calls["n"] == 2        # 두 번 다 실제 실행됨(빈 결과 미캐싱)


@pytest.mark.asyncio
async def test_nonempty_result_cached():
    """정상(비어있지 않은) 결과는 캐싱해 재호출 시 실제 실행하지 않는다."""
    calls = {"n": 0}

    @cache.cached(ttl=3600, key_prefix="test_ok")
    async def stable():
        calls["n"] += 1
        return [{"v": 1}]

    await stable()
    await stable()
    assert calls["n"] == 1  # 두 번째는 캐시 히트
