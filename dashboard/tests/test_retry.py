"""async_retry 데코레이터 단위 테스트."""
import pytest
import asyncio
from unittest.mock import AsyncMock
from dashboard.backend.utils.retry import async_retry


@pytest.mark.asyncio
async def test_retry_succeeds_on_third_attempt():
    """3번째 시도에서 성공하는 경우 결과를 정상 반환한다."""
    call_count = 0

    @async_retry(max_retries=3, backoff_base=0.01)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("일시적 오류")
        return "성공"

    result = await flaky()
    assert result == "성공"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    """최대 재시도 횟수를 초과하면 마지막 예외를 올린다."""
    @async_retry(max_retries=2, backoff_base=0.01)
    async def always_fail():
        raise ConnectionError("영구 오류")

    with pytest.raises(ConnectionError):
        await always_fail()


@pytest.mark.asyncio
async def test_on_failure_called_on_final_failure():
    """최종 실패 시 on_failure 콜백이 호출된다."""
    failure_cb = AsyncMock()

    @async_retry(max_retries=2, backoff_base=0.01, on_failure=failure_cb)
    async def always_fail():
        raise ValueError("항상 실패")

    with pytest.raises(ValueError):
        await always_fail()
    failure_cb.assert_called_once_with("always_fail", "항상 실패")


@pytest.mark.asyncio
async def test_on_failure_not_called_on_success():
    """성공 시 on_failure 콜백이 호출되지 않는다."""
    failure_cb = AsyncMock()

    @async_retry(max_retries=3, backoff_base=0.01, on_failure=failure_cb)
    async def succeeds():
        return "ok"

    result = await succeeds()
    assert result == "ok"
    failure_cb.assert_not_called()
