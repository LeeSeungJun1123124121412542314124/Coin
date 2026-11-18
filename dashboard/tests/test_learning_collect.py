"""학습 탭 온체인 수집 잡 테스트 (네트워크 호출 없음)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dashboard.backend.collectors import binance_spot
from dashboard.backend.collectors import learning_onchain as onchain
from dashboard.backend.jobs import learning_collect as jobs


@pytest.fixture
def state_db(tmp_path, monkeypatch):
    from dashboard.backend.db import connection
    monkeypatch.setattr(connection, "_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(connection, "_conn", None)
    connection.get_connection()
    yield connection
    if connection._conn is not None:
        connection._conn.close()
        connection._conn = None


@pytest.fixture
def sent(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake(job, err):
        calls.append((job, err))

    monkeypatch.setattr(jobs, "notify_job_failure", fake)
    return calls


def _raiser(exc):
    async def fn(*a, **k):
        raise exc
    return fn


def _ok(rows):
    async def fn(*a, **k):
        return rows
    return fn


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://secret.example/path?key=SECRET-KEY-1")
    return httpx.HTTPStatusError("boom https://secret.example", request=req,
                                 response=httpx.Response(status, request=req))


def _runs(source: str) -> list[dict]:
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT status, reason, is_retry FROM learning_collection_runs WHERE source=? ORDER BY id",
            (source,),
        ).fetchall()
    return [{"status": r[0], "reason": r[1], "is_retry": r[2]} for r in rows]


def _row(metric, scope, source):
    return [{"metric": metric, "scope": scope, "as_of": "2026-11-17", "value": 1.0, "source": source}]


def _stub_all(monkeypatch, **overrides):
    """모든 소스를 빈 성공으로 대체하고 일부만 덮어쓴다."""
    defaults = {
        "fetch_coinmetrics_btc": _ok(_row("mvrv", "BTC", "coinmetrics")),
        "fetch_mempool": _ok(_row("fee_fastest", "BTC", "mempool.space")),
        "fetch_defillama": _ok(_row("stablecoin_supply", "GLOBAL", "defillama")),
        "fetch_binance_futures": _ok([]),
        "fetch_bgeometrics_sopr": _ok(_row("sopr", "BTC", "bgeometrics")),
        "fetch_fred_liquidity": _ok(_row("tga", "US", "fred")),
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(onchain, name, fn)


def _add_symbol(symbol: str, status: str = "done") -> None:
    from dashboard.backend.db.connection import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT INTO learning_symbols(symbol, added_at, backfill_status) VALUES (?, 'x', ?)",
            (symbol, status),
        )


def test_jobs_scheduled() -> None:
    from dashboard.backend import main

    class DummyNotifier:
        async def send_message(self, message: str) -> None:
            return None

    class DummyDispatcher:
        _notifier = DummyNotifier()

    scheduler = AsyncIOScheduler(timezone="UTC")
    main._register_jobs(scheduler, config=object(), dispatcher=DummyDispatcher())
    assert str(scheduler.get_job("learning_daily").trigger) == "cron[hour='0', minute='10']"
    assert str(scheduler.get_job("learning_daily_retry").trigger) == "cron[hour='4', minute='0']"
    assert str(scheduler.get_job("learning_4h").trigger) == "cron[hour='0,4,8,12,16,20', minute='5']"


def test_nupl_realized() -> None:
    assert onchain.derive_nupl_realized(2.0, 60000.0) == (0.5, 30000.0)


@pytest.mark.asyncio
async def test_source_failure_recorded_and_alerted(state_db, sent, monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET-TOKEN-123")
    _stub_all(monkeypatch, fetch_coinmetrics_btc=_raiser(_http_error(429)))
    await jobs.collect_learning_daily()

    assert "learning:coinmetrics" in [j for j, _ in sent]
    assert all("SECRET" not in e and "http" not in e for _, e in sent)
    assert _runs("coinmetrics")[-1] == {"status": "failed", "reason": "HTTPStatusError: HTTP 429", "is_retry": 0}
    assert _runs("mempool.space")[-1]["status"] == "ok"  # 다른 소스는 영향 없음


@pytest.mark.asyncio
async def test_ok_run_saves_metrics_with_upsert(state_db, sent, monkeypatch) -> None:
    from dashboard.backend.db.connection import get_db
    _stub_all(monkeypatch)
    await jobs.collect_learning_daily()
    await jobs.collect_learning_daily()
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM learning_metrics WHERE metric='mvrv'").fetchone()[0]
    assert n == 1 and sent == []


@pytest.mark.asyncio
async def test_fred_empty_is_failure(state_db, sent, monkeypatch) -> None:
    async def empty():
        return []

    monkeypatch.setattr(onchain.fred, "fetch_tga", empty)
    monkeypatch.setattr(onchain.fred, "fetch_m2", empty)
    _stub_all(monkeypatch, fetch_fred_liquidity=onchain.fetch_fred_liquidity)
    await jobs.collect_learning_daily()
    reason = "FRED 값 없음(키 미설정 또는 조회 실패)"
    assert _runs("fred")[-1] == {"status": "failed", "reason": reason, "is_retry": 0}
    assert ("learning:fred", reason) in sent


@pytest.mark.asyncio
async def test_futures_skipped_when_no_futures(state_db, sent, monkeypatch) -> None:
    _add_symbol("ABCUSDT")
    _stub_all(monkeypatch)
    await jobs.collect_learning_daily()
    last = _runs("binance-futures")[-1]
    assert last["status"] == "skipped" and last["reason"]
    assert not any(j == "learning:binance-futures" for j, _ in sent)


@pytest.mark.asyncio
async def test_futures_failure_alerts_with_symbol_prefix(state_db, sent, monkeypatch) -> None:
    _add_symbol("SOLUSDT")
    _stub_all(monkeypatch, fetch_binance_futures=_raiser(_http_error(418)))
    await jobs.collect_learning_daily()
    assert _runs("binance-futures")[-1]["reason"] == "SOLUSDT: HTTPStatusError: HTTP 418"
    assert any(j == "learning:binance-futures" for j, _ in sent)


@pytest.mark.asyncio
async def test_daily_candles_incremental_and_skip_unbackfilled(state_db, sent, monkeypatch) -> None:
    _add_symbol("SOLUSDT")
    _add_symbol("NEWUSDT", "pending")
    binance_spot.save_candles("SOLUSDT", "1d", [
        {"open_time": 1000, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    calls = []

    async def fake_klines(symbol, interval, start_ms, end_ms=None, now_ms=None):
        calls.append((symbol, interval, start_ms))
        return [{"open_time": start_ms, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    monkeypatch.setattr(binance_spot, "fetch_klines", fake_klines)
    _stub_all(monkeypatch)
    await jobs.collect_learning_daily()
    step = binance_spot.INTERVAL_MS["1d"]
    assert calls == [("SOLUSDT", "1d", 1000 + step)]
    assert binance_spot.last_open_time("SOLUSDT", "1d") == 1000 + step
    assert _runs("binance-spot")[-1]["status"] == "ok"


def _seed_bg_runs(n: int, status: str = "ok", minutes_ago: int = 5) -> None:
    from dashboard.backend.db.connection import get_db
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    with get_db() as conn:
        for _ in range(n):
            conn.execute(
                "INSERT INTO learning_collection_runs(source, run_at, status) VALUES ('bgeometrics', ?, ?)",
                (ts, status),
            )


def test_bgeometrics_budget(state_db) -> None:
    now = datetime.now(timezone.utc)
    assert jobs.bgeometrics_budget_ok(now)
    _seed_bg_runs(7)
    assert jobs.bgeometrics_budget_ok(now)
    _seed_bg_runs(1)  # 1시간 내 8회
    assert not jobs.bgeometrics_budget_ok(now)


def test_bgeometrics_budget_daily_and_ignores_skipped(state_db) -> None:
    now = datetime.now(timezone.utc)
    _seed_bg_runs(20, status="skipped")
    _seed_bg_runs(14, minutes_ago=300)  # 24시간 내, 1시간 밖
    assert jobs.bgeometrics_budget_ok(now)
    _seed_bg_runs(1, minutes_ago=300)
    assert not jobs.bgeometrics_budget_ok(now)


@pytest.mark.asyncio
async def test_bgeometrics_over_budget_records_rate_limited_without_http(state_db, sent, monkeypatch) -> None:
    _seed_bg_runs(15, minutes_ago=300)
    called = []

    async def spy():
        called.append(1)
        return []

    _stub_all(monkeypatch, fetch_bgeometrics_sopr=spy)
    await jobs.collect_learning_daily()
    assert called == []
    assert _runs("bgeometrics")[-1]["status"] == "rate_limited"
    assert not any(j == "learning:bgeometrics" for j, _ in sent)


@pytest.mark.asyncio
async def test_retry_only_failed_or_stale_sources(state_db, sent, monkeypatch) -> None:
    from dashboard.backend.db.connection import get_db
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    with get_db() as conn:  # mvrv가 어제 값이라 coinmetrics는 stale 아님
        conn.execute("INSERT INTO learning_metrics(metric, scope, as_of, value) VALUES ('mvrv','BTC',?,1)", (yesterday,))
    jobs._record_run("defillama", "failed", "x")
    jobs._record_run("mempool.space", "failed", "x")
    jobs._record_run("mempool.space", "ok")  # 최신이 ok면 제외
    jobs._record_run("fred", "rate_limited", "x")
    seen = []

    def spy(name):
        async def fn():
            seen.append(name)
            return _row("m", "S", name)
        return fn

    _stub_all(monkeypatch, fetch_defillama=spy("defillama"), fetch_mempool=spy("mempool"),
              fetch_fred_liquidity=spy("fred"), fetch_coinmetrics_btc=spy("coinmetrics"))
    await jobs.retry_learning_daily()
    assert sorted(seen) == ["defillama", "fred"]
    assert _runs("defillama")[-1]["is_retry"] == 1


@pytest.mark.asyncio
async def test_retry_coinmetrics_when_mvrv_missing(state_db, sent, monkeypatch) -> None:
    seen = []

    async def cm():
        seen.append("coinmetrics")
        return []

    _stub_all(monkeypatch, fetch_coinmetrics_btc=cm)
    await jobs.retry_learning_daily()  # mvrv 없음
    assert seen == ["coinmetrics"]


def _boom_list_symbols():
    raise RuntimeError("db error https://secret.example?key=SECRET-KEY-1")


@pytest.mark.asyncio
async def test_list_symbols_failure_recorded_and_alerted_daily(state_db, sent, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "list_symbols", _boom_list_symbols)
    _stub_all(monkeypatch)
    await jobs.collect_learning_daily()
    for src in ("binance-futures", "binance-spot"):
        assert _runs(src)[-1] == {"status": "failed", "reason": "RuntimeError", "is_retry": 0}
        assert (f"learning:{src}", "RuntimeError") in sent
    assert all("SECRET" not in e for _, e in sent)


@pytest.mark.asyncio
async def test_list_symbols_failure_recorded_and_alerted_4h(state_db, sent, monkeypatch) -> None:
    monkeypatch.setattr(jobs, "list_symbols", _boom_list_symbols)
    await jobs.collect_learning_4h()
    assert _runs("binance-spot")[-1] == {"status": "failed", "reason": "RuntimeError", "is_retry": 0}
    assert sent == [("learning:binance-spot", "RuntimeError")]


@pytest.mark.asyncio
async def test_retry_runner_unexpected_error_recorded_and_alerted(state_db, sent, monkeypatch) -> None:
    jobs._record_run("binance-futures", "failed", "x")
    monkeypatch.setattr(jobs, "list_symbols", _boom_list_symbols)
    _stub_all(monkeypatch)
    await jobs.retry_learning_daily()
    assert _runs("binance-futures")[-1] == {"status": "failed", "reason": "RuntimeError", "is_retry": 1}
    assert ("learning:binance-futures", "RuntimeError") in sent
