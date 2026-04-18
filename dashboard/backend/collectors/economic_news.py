"""경제 뉴스 RSS 컬렉터 — 연합뉴스·한국경제·Google News."""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from dashboard.backend.cache import cached

logger = logging.getLogger(__name__)

_RSS_FEEDS = [
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("한국경제", "https://www.hankyung.com/feed/economy"),
    ("Google News", "https://news.google.com/rss/search?q=%EA%B2%BD%EC%A0%9C&hl=ko&gl=KR&ceid=KR:ko"),
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


async def _fetch_feed(client: httpx.AsyncClient, source: str, url: str) -> list[dict]:
    """단일 RSS 피드 파싱."""
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        # RSS 2.0: channel > item
        for item in root.findall(".//item")[:10]:
            title_el = item.find("title")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")
            if title_el is None or link_el is None:
                continue
            title = (title_el.text or "").strip()
            link = (link_el.text or "").strip()
            pub_date = ""
            if pubdate_el is not None and pubdate_el.text:
                try:
                    pub_date = parsedate_to_datetime(pubdate_el.text).isoformat()
                except Exception:
                    pub_date = pubdate_el.text.strip()
            if title and link:
                items.append({"title": title, "link": link, "pub_date": pub_date, "source": source})
        return items
    except Exception as e:
        logger.warning("RSS 피드 조회 실패 (%s): %s", source, e)
        return []


@cached(ttl=900, key_prefix="economic_news")
async def fetch_economic_news(limit: int = 6) -> list[dict]:
    """RSS 3종 파싱 후 최신순 정렬, limit개 반환."""
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_feed(client, source, url) for source, url in _RSS_FEEDS],
            return_exceptions=True,
        )

    all_items: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_items.extend(r)

    # pub_date 기준 내림차순 정렬 (ISO 형식이므로 문자열 비교 가능)
    all_items.sort(key=lambda x: x.get("pub_date", ""), reverse=True)

    # URL 기준 중복 제거 (순서 유지)
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        if item["link"] not in seen:
            seen.add(item["link"])
            deduped.append(item)

    return deduped[:limit]
