"""CNN Fear & Greed 지수 수집기."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

import httpx


CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    # CNN은 축약형 UA('Mozilla/5.0')를 봇으로 판정해 418을 반환하므로 완전한 브라우저 UA 필수
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
}


def _as_float(value: Any) -> float:
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return float(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_datetime(int(raw))
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            try:
                parsed_date = date.fromisoformat(raw[:10])
            except ValueError:
                return None
            return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    return None


def _find_current_candidate(payload: dict[str, Any]) -> dict[str, Any] | None:
    current = payload.get("fear_and_greed")
    if isinstance(current, dict):
        return current
    current = payload.get("fearGreed")
    if isinstance(current, dict):
        return current
    return None


def _find_history_candidate(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("fear_and_greed_historical", "fearGreedHistorical", "historical"):
        section = payload.get(key)
        if isinstance(section, dict):
            data = section.get("data")
        else:
            data = section
        if isinstance(data, list) and data:
            latest = data[-1]
            if isinstance(latest, dict):
                return latest
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[-1], dict):
        return data[-1]
    return None


def _value_from(candidate: dict[str, Any]) -> float:
    for key in ("score", "value", "y"):
        if key in candidate and candidate[key] is not None:
            return _as_float(candidate[key])
    raise ValueError("CNN Fear & Greed value가 없습니다")


def _rating_from(candidate: dict[str, Any]) -> str | None:
    for key in ("rating", "classification", "value_classification"):
        value = candidate.get(key)
        if value is not None:
            return str(value)
    return None


def _updated_at_from(candidate: dict[str, Any]) -> datetime:
    for key in ("updated_at", "timestamp", "date", "x"):
        parsed = _parse_datetime(candidate.get(key))
        if parsed is not None:
            return parsed
    raise ValueError("CNN Fear & Greed 갱신 시간이 없습니다")


def parse_fear_greed_payload(payload: dict[str, Any]) -> dict:
    """CNN 응답에서 DB 저장용 최신 Fear & Greed 레코드를 추출한다."""
    candidate = _find_current_candidate(payload) or _find_history_candidate(payload)
    if candidate is None:
        raise ValueError("CNN Fear & Greed 응답 구조를 찾을 수 없습니다")

    updated_at = _updated_at_from(candidate)
    return {
        "date": updated_at.date().isoformat(),
        "value": _value_from(candidate),
        "rating": _rating_from(candidate),
        "updated_at": updated_at.isoformat(),
    }


async def fetch_fear_greed() -> dict:
    async with httpx.AsyncClient(
        timeout=10,
        headers=_HEADERS,
    ) as client:
        resp = await client.get(CNN_FEAR_GREED_URL)
        resp.raise_for_status()
        return parse_fear_greed_payload(resp.json())
