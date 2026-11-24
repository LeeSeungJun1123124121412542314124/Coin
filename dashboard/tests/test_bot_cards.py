"""봇 리포트로 만드는 리서치 '봇 관찰' 카드 (docs/plans/bot-reports-spec-2026-11-24.md 7절)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
import sqlite3

import pytest

from dashboard.backend.db.connection import _init_schema

TODAY = date(2026, 11, 24)

HEATMAP_DATA = {
    "price": 61150,
    "main_long_band": {"price": 57352, "amount_3d_m": 63.8, "amount_1w_m": 63.8},
    "long_pct": {"24h": 36, "3d": 71, "1w": 50},
    "short_pct": {"24h": 64, "3d": 29, "1w": 50},
    "biggest_short": {"price": 64001, "amount_m": 62.9},
    "liquidated_24h": {"total_m": 97.0, "long_m": 34.7, "short_m": 62.3},
}

# 2026-11-24에 봇이 실제로 보낸 본문에서 가져온 형태 (−는 U+2212)
DAILY_BODY = """**☀️ 11/24 일봉 점검 · 09:05 KST**

| 상태 | 조건 | 현재 | 기준 | 남은 거리 | 출처 |
|---|---|---|---|---|---|
| 🟡 | BTC $60K (6월 저점 상단) | $61,150 | $60,000 | +1.92% | CoinGecko |

**현물 ETF 순유입 (Farside)**

| 날짜 | BTC | ETH | SOL | 비고 |
|---|---|---|---|---|
| 11/23 | −$73.7M | $0.0M | −$1.9M | 잠정치. BTC는 IBIT·FBTC 미집계 |
| 11/20 | −$669.2M | −$97.3M | −$5.9M | 어제 잠정(BTC −$124.5M)에서 미집계분이 반영된 확정치 |
| 11/19 | −$582.3M | −$131.2M | +$1.1M | 확정치 유지 |

**뉴스**

- 뉴스 한 줄"""

WHALE_BODY = """**🐋 고래·온체인 (X)** · 11-24 09:43 KST

| 시각(KST) | 계정 | 코인 | 사실 | 링크 |
|---|---|---|---|---|
| 11-23 23:55 | Onchain Lens | BTC | Abraxas Capital, Kraken에서 2,223 BTC(약 $140.74M) 추가 수신 | [글](https://x.com/OnchainLens/status/1) |
| 🔴 11-24 00:22 | Whale Alert | ETH | 29,624 ETH($53,029,090) 미확인 지갑→Coinbase Institutional 입금 | [글](https://x.com/whale_alert/status/2) |
| 11-24 00:57 | Whale Alert | BTC | **4,362 BTC**($274,185,079) Coinbase Institutional→신규 미확인 지갑 이동 | [글](https://x.com/whale_alert/status/3) |

출처: [Onchain Lens](https://x.com/OnchainLens/status/1)"""


@pytest.fixture
def conn(monkeypatch):
    from dashboard.backend.db import connection

    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    _init_schema(c)

    @contextmanager
    def fake_get_db():
        yield c

    monkeypatch.setattr(connection, "get_db", fake_get_db)
    return c


def _add(conn, kind: str, reported_at: str, body: str = "본문", data: dict | None = None, title: str = "제목") -> int:
    cur = conn.execute(
        """INSERT INTO bot_reports (kind, title, body, data_json, reported_at, received_at, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (kind, title, body, json.dumps(data) if data is not None else None, reported_at, reported_at,
         f"{kind}-{reported_at}-{len(body)}"),
    )
    return cur.lastrowid


def _by_key(cards: list[dict]) -> dict[str, dict]:
    return {card["key"]: card for card in cards}


def test_heatmap_card_summarizes_bands_ratio_and_liquidations(conn) -> None:
    from dashboard.backend.services import bot_cards

    report_id = _add(conn, "heatmap", "2026-11-24T00:13:00+00:00", data=HEATMAP_DATA)

    card = _by_key(bot_cards.build_bot_cards(TODAY))["bot_heatmap"]

    assert card["name"] == "청산 히트맵"
    assert card["observed"] is True
    assert card["title"] == "아래 롱 $57,352 · 위 숏 $64,001"
    assert card["summary"] == (
        "11-24 09:13 기준 · 현재가 $61,150 | 아래 롱 $57,352 (-6.2%) 63.8M"
        " | 위 숏 $64,001 (+4.7%) 62.9M | 3일 롱/숏 71/29 | 24시간 청산 $97.0M"
    )
    assert ["24시간 청산", "$97.0M (롱 $34.7M · 숏 $62.3M)"] in card["details"]["rows"]
    assert ["롱/숏 비중", "24시간 36/64 · 3일 71/29 · 1주 50/50"] in card["details"]["rows"]
    assert card["details"]["report_id"] == report_id
    assert card["compare"] == {"prev": None, "week": None}


def test_heatmap_card_shows_only_fields_that_exist(conn) -> None:
    """봇이 보내는 data 모양이 바뀌거나 빠져도 오류 없이 있는 항목만 보여준다."""
    from dashboard.backend.services import bot_cards

    _add(conn, "heatmap", "2026-11-24T00:13:00+00:00", data={"price": 61150, "long_pct": "모름", "biggest_short": {"price": "많음"}})
    _add(conn, "heatmap", "2026-11-23T00:13:00+00:00", data=None, title="CoinGlass 청산 히트맵 · 11/23")

    card = _by_key(bot_cards.build_bot_cards(TODAY))["bot_heatmap"]

    assert card["summary"] == "11-24 09:13 기준 · 현재가 $61,150"
    assert card["title"] == "청산 히트맵"
    # 어제 리포트에는 숫자 값이 없었다 — 요약 대신 그 리포트의 제목을 보여준다
    assert card["compare"]["prev"] == {"date": "2026-11-23", "days_ago": 1, "summary": "CoinGlass 청산 히트맵 · 11/23"}


def test_etf_card_reads_latest_row_of_etf_table(conn) -> None:
    from dashboard.backend.services import bot_cards

    _add(conn, "daily_check", "2026-11-24T00:06:00+00:00", body=DAILY_BODY)

    card = _by_key(bot_cards.build_bot_cards(TODAY))["bot_etf"]

    assert card["name"] == "ETF 수급"
    assert card["observed"] is True
    assert card["title"] == "BTC 현물 ETF -$73.7M (11/23 잠정)"
    assert card["summary"] == "11/23 잠정 · BTC -$73.7M | ETH $0.0M | SOL -$1.9M"
    assert card["details"]["rows"] == [
        ["11/23 (잠정)", "BTC -$73.7M · ETH $0.0M · SOL -$1.9M"],
        ["11/20", "BTC -$669.2M · ETH -$97.3M · SOL -$5.9M"],
        ["11/19", "BTC -$582.3M · ETH -$131.2M · SOL +$1.1M"],
    ]


def test_etf_card_is_skipped_when_table_is_missing(conn) -> None:
    from dashboard.backend.services import bot_cards

    _add(conn, "daily_check", "2026-11-24T00:06:00+00:00", body="| 상태 | 조건 |\n|---|---|\n| 🟡 | BTC |\n\nETF 표가 없는 날")

    assert "bot_etf" not in _by_key(bot_cards.build_bot_cards(TODAY))


def test_whale_card_counts_items_by_coin_and_lists_them(conn) -> None:
    from dashboard.backend.services import bot_cards

    _add(conn, "whale", "2026-11-24T00:43:00+00:00", body=WHALE_BODY)

    card = _by_key(bot_cards.build_bot_cards(TODAY))["bot_whale"]

    assert card["name"] == "고래 소식"
    assert card["title"] == "고래·온체인 소식 3건"
    assert card["summary"] == "11-24 09:43 기준 · 소식 3건 | BTC 2건 · ETH 1건 | 🔴 1건"
    assert card["details"]["rows"] == [
        ["11-23 23:55 · Onchain Lens · BTC", "Abraxas Capital, Kraken에서 2,223 BTC(약 $140.74M) 추가 수신"],
        ["🔴 11-24 00:22 · Whale Alert · ETH", "29,624 ETH($53,029,090) 미확인 지갑→Coinbase Institutional 입금"],
        ["11-24 00:57 · Whale Alert · BTC", "4,362 BTC($274,185,079) Coinbase Institutional→신규 미확인 지갑 이동"],
    ]


def test_cards_use_latest_report_and_compare_with_previous_kst_day(conn) -> None:
    from dashboard.backend.services import bot_cards

    older = {**HEATMAP_DATA, "price": 58970}
    _add(conn, "heatmap", "2026-11-22T00:17:00+00:00", data=older)          # 11-22 09:17 KST
    _add(conn, "heatmap", "2026-11-23T15:30:00+00:00", data=HEATMAP_DATA)   # 11-24 00:30 KST (오늘, 먼저 온 것)
    _add(conn, "heatmap", "2026-11-24T00:13:00+00:00", data={**HEATMAP_DATA, "price": 61200})  # 오늘 최신

    card = _by_key(bot_cards.build_bot_cards(TODAY))["bot_heatmap"]

    assert "현재가 $61,200" in card["summary"]
    # 같은 날 먼저 온 리포트가 아니라, 그 전 날짜의 리포트와 비교한다
    assert card["compare"]["prev"]["date"] == "2026-11-22"
    assert card["compare"]["prev"]["days_ago"] == 2
    assert "현재가 $58,970" in card["compare"]["prev"]["summary"]
    assert card["compare"]["week"] is None


def test_card_is_skipped_when_latest_report_is_older_than_7_days(conn) -> None:
    from dashboard.backend.services import bot_cards

    _add(conn, "heatmap", "2026-11-16T00:13:00+00:00", data=HEATMAP_DATA)   # 8일 전
    _add(conn, "whale", "2026-11-17T00:43:00+00:00", body=WHALE_BODY)        # 7일 전 — 아직 보여준다

    cards = _by_key(bot_cards.build_bot_cards(TODAY))

    assert "bot_heatmap" not in cards
    assert "bot_whale" in cards


def test_no_reports_means_no_cards(conn) -> None:
    from dashboard.backend.services import bot_cards

    assert bot_cards.build_bot_cards(TODAY) == []


def test_cards_come_in_fixed_order(conn) -> None:
    from dashboard.backend.services import bot_cards

    _add(conn, "whale", "2026-11-24T00:43:00+00:00", body=WHALE_BODY)
    _add(conn, "heatmap", "2026-11-24T00:13:00+00:00", data=HEATMAP_DATA)
    _add(conn, "daily_check", "2026-11-24T00:06:00+00:00", body=DAILY_BODY)

    assert [c["key"] for c in bot_cards.build_bot_cards(TODAY)] == ["bot_etf", "bot_heatmap", "bot_whale"]


def _scored(key: str, score: int) -> dict:
    return {"key": key, "name": key, "level": "neutral", "score": score, "title": key, "summary": key,
            "details": {"x": 1}, "updated_at": "2026-11-24T00:00:00+00:00"}


@pytest.mark.asyncio
async def test_route_appends_bot_cards_after_scored_cards(conn, monkeypatch) -> None:
    from dashboard.backend.api import research_routes

    _add(conn, "heatmap", "2026-11-24T00:13:00+00:00", data=HEATMAP_DATA)

    async def fake_analyze_all() -> dict:
        return {"generated_at": "t", "categories": [_scored("onchain", 42)]}

    monkeypatch.setattr(research_routes, "analyze_all", fake_analyze_all)
    monkeypatch.setattr(research_routes, "kst_today", lambda: TODAY)

    body = json.loads((await research_routes.get_research_analysis()).body)

    assert [c["key"] for c in body["categories"]] == ["onchain", "bot_heatmap"]
    assert body["categories"][1]["observed"] is True


@pytest.mark.asyncio
async def test_route_keeps_scored_cards_when_bot_cards_fail(conn, monkeypatch) -> None:
    from dashboard.backend.api import research_routes

    async def fake_analyze_all() -> dict:
        return {"generated_at": "t", "categories": [_scored("onchain", 42)]}

    def broken(day):
        raise ValueError("봇 리포트 해석 실패")

    monkeypatch.setattr(research_routes, "analyze_all", fake_analyze_all)
    monkeypatch.setattr(research_routes, "build_bot_cards", broken)

    response = await research_routes.get_research_analysis()

    assert response.status_code == 200
    assert [c["key"] for c in json.loads(response.body)["categories"]] == ["onchain"]


def test_snapshot_skips_observed_cards(conn) -> None:
    """봇 관찰 카드는 점수가 없다 — 점수 스냅샷에 0점으로 섞여 들어가면 안 된다."""
    from dashboard.backend.services import bot_cards, research_history

    _add(conn, "heatmap", "2026-11-24T00:13:00+00:00", data=HEATMAP_DATA)
    cards = bot_cards.build_bot_cards(TODAY)

    assert research_history.save_snapshot([_scored("onchain", 42), *cards], TODAY) == 1
