"""비동기 재시도 데코레이터."""
from __future__ import annotations

import asyncio
import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


def async_retry(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple = (Exception,),
    on_failure: Callable | None = None,
):
    """지수 백오프 재시도 데코레이터.

    Args:
        max_retries: 최대 재시도 횟수
        backoff_base: 백오프 기저값 (backoff_base ** attempt 초)
        exceptions: 재시도할 예외 타입
        on_failure: 최종 실패 시 호출할 async 콜백 (job_name: str, error: str) -> None
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries:
                        delay = backoff_base ** attempt
                        logger.warning(
                            "%s 재시도 %d/%d (%.1fs 후): %s",
                            func.__name__, attempt, max_retries, delay, e,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "%s 최종 실패 (%d회 시도): %s",
                            func.__name__, max_retries, e,
                        )
                        if on_failure is not None:
                            try:
                                await on_failure(func.__name__, str(e))
                            except Exception as cb_exc:
                                logger.error("on_failure 콜백 실패: %s", cb_exc)
            raise last_exc  # type: ignore[misc]

        return wrapper
    return decorator
