"""TTL 기반 인메모리 캐시 — 데코레이터와 직접 호출 모두 지원."""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any

# { cache_key: (value, expire_at) }
_store: dict[str, tuple[Any, float]] = {}


def get(key: str) -> Any | None:
    """캐시 조회. 만료됐거나 없으면 None 반환."""
    entry = _store.get(key)
    if entry is None:
        return None
    value, expire_at = entry
    if time.monotonic() > expire_at:
        del _store[key]
        return None
    return value


def set(key: str, value: Any, ttl: int) -> None:
    """캐시 저장. ttl: 초 단위."""
    _store[key] = (value, time.monotonic() + ttl)


def delete(key: str) -> None:
    _store.pop(key, None)


def delete_prefix(prefix: str) -> None:
    """prefix로 시작하는 모든 캐시 키 삭제."""
    for k in list(_store.keys()):
        if k.startswith(prefix):
            del _store[k]


def cached(ttl: int, key_prefix: str = ""):
    """비동기 함수용 TTL 캐시 데코레이터.

    사용 예:
        @cached(ttl=60, key_prefix="coingecko")
        async def fetch_prices(): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix or fn.__name__}:{args}:{kwargs}"
            cached_value = get(cache_key)
            if cached_value is not None:
                return cached_value
            result = await fn(*args, **kwargs)
            if result is not None:
                set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
