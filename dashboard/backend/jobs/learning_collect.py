"""학습 탭 온체인·캔들 수집 잡 — 소스별 실행 이력 기록과 실패 알림."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from dashboard.backend.collectors import binance_spot
from dashboard.backend.collectors import learning_onchain as onchain
from dashboard.backend.db.connection import get_db
from dashboard.backend.services.learning_symbols import backfill_symbol, list_symbols
from dashboard.backend.utils.alerting import notify_job_failure

logger = logging.getLogger(__name__)

SPOT_SOURCE = "binance-spot"
SPOT_1H_SOURCE = "binance-spot-1h"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _reason(e: Exception) -> str:
    """사유 문자열 — httpx 예외의 str(e)는 URL을 담으므로 사용하지 않는다."""
    if isinstance(e, onchain.SourceError):
        return str(e)
    if isinstance(e, httpx.HTTPStatusError):
        return f"{type(e).__name__}: HTTP {e.response.status_code}"
    return type(e).__name__


def _record_run(source: str, status: str, reason: str | None = None, is_retry: bool = False) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO learning_collection_runs (source, run_at, status, reason, is_retry) "
            "VALUES (?, ?, ?, ?, ?)",
            (source, _utc_now().isoformat(), status, reason, 1 if is_retry else 0),
        )


def _save_metrics(rows: list[dict]) -> None:
    fetched_at = _utc_now().isoformat()
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO learning_metrics (metric, scope, as_of, value, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(metric, scope, as_of) DO UPDATE SET
                 value=excluded.value, source=excluded.source, fetched_at=excluded.fetched_at""",
            [(r["metric"], r["scope"], r["as_of"], r["value"], r["source"], fetched_at) for r in rows],
        )


async def _fail(source: str, reason: str, is_retry: bool) -> None:
    _record_run(source, "failed", reason, is_retry)
    await notify_job_failure(f"learning:{source}", reason)


def bgeometrics_budget_ok(now: datetime) -> bool:
    """BGeometrics 무료 한도 — 최근 1시간 8회 미만, 24시간 15회 미만 (ok·failed만 집계)."""
    def _count(delta: timedelta) -> int:
        since = (now - delta).isoformat()
        with get_db() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM learning_collection_runs "
                "WHERE source='bgeometrics' AND status IN ('ok','failed') AND run_at >= ?",
                (since,),
            ).fetchone()[0]

    return _count(timedelta(hours=1)) < 8 and _count(timedelta(hours=24)) < 15


async def _collect_source(source: str, fetch, is_retry: bool) -> None:
    """단일 소스: 조회 → 저장 → 이력 기록. 실패는 기록 + 알림."""
    try:
        rows = await fetch()
        _save_metrics(rows)
        _record_run(source, "ok", None, is_retry)
    except Exception as e:  # 소스 하나의 실패가 다른 소스를 막지 않도록 격리
        await _fail(source, _reason(e), is_retry)


async def _collect_bgeometrics(is_retry: bool) -> None:
    if not bgeometrics_budget_ok(_utc_now()):
        _record_run("bgeometrics", "rate_limited", "무료 호출 한도 초과(시간당 8·일 15)", is_retry)
        return
    await _collect_source("bgeometrics", onchain.fetch_bgeometrics_sopr, is_retry)


async def _collect_futures(is_retry: bool) -> None:
    saved = 0
    errors: list[str] = []
    for item in list_symbols():
        sym = item["symbol"]
        try:
            rows = await onchain.fetch_binance_futures(sym)
            if rows:
                _save_metrics(rows)
                saved += len(rows)
        except Exception as e:
            errors.append(f"{sym}: {_reason(e)}")
    if errors:
        await _fail("binance-futures", "; ".join(errors), is_retry)
    elif saved:
        _record_run("binance-futures", "ok", None, is_retry)
    else:
        _record_run("binance-futures", "skipped", "선물 없는 종목이거나 추적 종목 없음", is_retry)


async def _collect_candles(
    intervals: tuple[str, ...], is_retry: bool = False, source: str = SPOT_SOURCE, alert: bool = True
) -> None:
    """시간봉별 캔들 증분 수집. 백필 미완 종목은 상장일부터 전체 백필(종목당 한 번),
    백필 완료인데 해당 시간봉만 비어 있으면 그 시간봉만 처음부터 받는다."""
    errors: list[str] = []
    for item in list_symbols():
        sym = item["symbol"]
        if item["backfill_status"] != "done":
            # backfill_symbol은 예외를 던지지 않고 failed 상태로 돌려준다 — 실패도 이 실행의 오류로 기록
            if (await backfill_symbol(sym))["status"] != "done":
                errors.append(f"{sym}: 백필 실패")
            continue
        for interval in intervals:
            last = binance_spot.last_open_time(sym, interval)
            try:
                bars = await binance_spot.fetch_klines(sym, interval, 0 if last is None else last + 1)
                binance_spot.save_candles(sym, interval, bars)
            except Exception as e:
                errors.append(f"{sym} {interval}: {_reason(e)}")
    if not errors:
        _record_run(source, "ok", None, is_retry)
    elif alert:
        await _fail(source, "; ".join(errors), is_retry)
    else:
        _record_run(source, "failed", "; ".join(errors), is_retry)


def _source_runners(is_retry: bool) -> dict:
    """소스명 → 실행 코루틴 팩토리 (collector 함수는 호출 시점에 모듈 속성으로 조회)."""
    return {
        "coinmetrics": lambda: _collect_source("coinmetrics", onchain.fetch_coinmetrics_btc, is_retry),
        "mempool.space": lambda: _collect_source("mempool.space", onchain.fetch_mempool, is_retry),
        "defillama": lambda: _collect_source("defillama", onchain.fetch_defillama, is_retry),
        "binance-futures": lambda: _collect_futures(is_retry),
        "bgeometrics": lambda: _collect_bgeometrics(is_retry),
        "fred": lambda: _collect_source("fred", onchain.fetch_fred_liquidity, is_retry),
        SPOT_SOURCE: lambda: _collect_candles(("1d", "1w", "1M"), is_retry),
    }


async def _guarded(name: str, fn, is_retry: bool) -> None:
    """러너 밖(list_symbols 등)에서 발생한 예외도 failed 기록 + 알림으로 처리."""
    try:
        await fn()
    except Exception as e:
        await _fail(name, _reason(e), is_retry)


async def _run_all(runners: dict, is_retry: bool) -> None:
    results = await asyncio.gather(
        *(_guarded(name, fn, is_retry) for name, fn in runners.items()), return_exceptions=True
    )
    for name, res in zip(runners, results):
        if isinstance(res, Exception):  # 기록·알림 자체가 실패한 경우만 여기 도달
            logger.error("학습 수집 실패 기록 오류 (%s): %s", name, type(res).__name__)


async def collect_learning_daily() -> None:
    """1d 캔들과 온체인·거시 소스 전부를 서로 독립적으로 수집."""
    await _run_all(_source_runners(False), False)


async def collect_learning_4h() -> None:
    await _guarded(SPOT_SOURCE, lambda: _collect_candles(("4h",)), False)


async def collect_learning_1h() -> None:
    """1h 캔들 — 알림·재시도 없이 별도 소스명으로만 기록(일봉 실패 이력을 가리지 않는다)."""
    try:
        await _collect_candles(("1h",), source=SPOT_1H_SOURCE, alert=False)
    except Exception as e:
        _record_run(SPOT_1H_SOURCE, "failed", _reason(e))


def _stale_sources() -> list[str]:
    """오늘(UTC) 최신 실행이 failed/rate_limited인 소스 + MVRV가 어제보다 오래된 coinmetrics."""
    today = _utc_now().strftime("%Y-%m-%d")
    with get_db() as conn:
        runs = conn.execute(
            "SELECT source, status FROM learning_collection_runs "
            "WHERE substr(run_at, 1, 10) = ? ORDER BY id",
            (today,),
        ).fetchall()
        mvrv = conn.execute(
            "SELECT MAX(as_of) FROM learning_metrics WHERE metric='mvrv' AND scope='BTC'"
        ).fetchone()[0]
    latest = {src: status for src, status in runs}  # id 오름차순이라 마지막 값이 최신
    stale = [s for s, st in latest.items() if st in ("failed", "rate_limited")]
    yesterday = (_utc_now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if (mvrv is None or mvrv < yesterday) and "coinmetrics" not in stale:
        stale.append("coinmetrics")
    return stale


async def retry_learning_daily() -> None:
    runners = _source_runners(True)
    targets = {s: runners[s] for s in _stale_sources() if s in runners}
    await _run_all(targets, True)
