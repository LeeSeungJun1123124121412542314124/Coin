"""시간 변환 유틸리티."""

from __future__ import annotations

from datetime import datetime


def iso_to_epoch_ms(value: str) -> int:
    """ISO 8601 문자열을 UTC epoch millisecond로 변환한다."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone 정보가 포함된 ISO 8601 문자열이어야 합니다")
    return int(dt.timestamp() * 1000)
