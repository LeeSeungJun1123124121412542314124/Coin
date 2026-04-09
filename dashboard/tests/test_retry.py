"""async_retry 데코레이터 단위 테스트."""
import pytest
import asyncio
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
