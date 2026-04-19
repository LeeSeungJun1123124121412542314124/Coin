"""
자동 백테스트 서비스

coin_ohlcv_1h 테이블에서 OHLCV 데이터를 불러와 13개 기술적 지표 시그널을 실행하고,
각 지표별 방향 적중률 및 수익률 통계를 계산한다.
결과는 auto_backtest_cache 테이블에 1시간 TTL로 캐시된다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone

import numpy as np

from dashboard.backend.db.connection import get_db
from dashboard.backend.services.ta_indicators import (
    signals_adx,
    signals_atr,
    signals_bollinger,
    signals_ema,
    signals_fibonacci,
    signals_ichimoku,
    signals_ma,
    signals_macd,
    signals_rsi,
    signals_stochastic,
    signals_support_resistance,
    signals_trendline,
    signals_volume,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _load_ohlcv(symbol: str, lookback: int) -> dict | None:
    """coin_ohlcv_1h에서 OHLCV 데이터 로드.

    Returns dict with numpy arrays: closes, highs, lows, volumes, timestamps
    Returns None if fewer than 60 bars available (minimum for any indicator).
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, open, high, low, close, volume "
            "FROM coin_ohlcv_1h "
            "WHERE symbol=? "
            "ORDER BY timestamp DESC LIMIT ?",
            (symbol, lookback),
        ).fetchall()

    if not rows:
        return None

    # DESC로 가져왔으니 오래된 순서로 뒤집기 (oldest first, newest last)
    rows = list(reversed(rows))

    if len(rows) < 60:
        return None

    timestamps = np.array([r[0] for r in rows], dtype=np.int64)
    opens      = np.array([r[1] for r in rows], dtype=np.float64)
    highs      = np.array([r[2] for r in rows], dtype=np.float64)
    lows       = np.array([r[3] for r in rows], dtype=np.float64)
    closes     = np.array([r[4] for r in rows], dtype=np.float64)
    volumes    = np.array([r[5] for r in rows], dtype=np.float64)

    return {
        "timestamps": timestamps,
        "opens":      opens,
        "highs":      highs,
        "lows":       lows,
        "closes":     closes,
        "volumes":    volumes,
        "bar_count":  len(rows),
    }


def _calc_indicator_stats(
    name: str,
    signals: list[tuple[int, str]],
    closes: np.ndarray,
    horizon_h: int,
) -> dict:
    """시그널 리스트와 종가 배열로 지표별 통계를 계산한다.

    horizon_h 봉 앞이 배열 범위를 벗어나거나 price_now == 0인 시그널은 제외된다.
    """
    n = len(closes)
    evaluated_count = 0
    hit_count = 0
    return_pcts: list[float] = []
    long_signals = 0
    short_signals = 0

    for i, direction in signals:
        future_idx = i + horizon_h
        if future_idx >= n:
            # 미래 봉이 범위 밖 → 제외
            continue

        price_now = closes[i]
        if price_now == 0:
            continue

        evaluated_count += 1

        # long/short 카운트 (평가 가능한 시그널만)
        if direction == "long":
            long_signals += 1
        else:
            short_signals += 1

        price_future = closes[future_idx]
        raw_ret = (price_future - price_now) / price_now * 100.0

        if direction == "long":
            is_hit = price_future > price_now
            ret_pct = raw_ret
        else:  # short
            is_hit = price_future < price_now
            ret_pct = -raw_ret  # 가격 하락 = 숏 수익

        if is_hit:
            hit_count += 1
        return_pcts.append(ret_pct)

    signal_count = evaluated_count

    if signal_count == 0:
        hit_rate        = 0.0
        avg_return_pct  = 0.0
        max_win_pct     = 0.0
        max_loss_pct    = 0.0
    else:
        hit_rate       = hit_count / signal_count * 100.0
        avg_return_pct = float(np.mean(return_pcts)) if return_pcts else 0.0
        max_win_pct    = float(max(return_pcts)) if return_pcts else 0.0
        max_loss_pct   = float(min(return_pcts)) if return_pcts else 0.0

    return {
        "name":           name,
        "signal_count":   signal_count,
        "long_signals":   long_signals,
        "short_signals":  short_signals,
        "hit_count":      hit_count,
        "hit_rate":       round(hit_rate, 2),
        "avg_return_pct": round(avg_return_pct, 4),
        "max_win_pct":    round(max_win_pct, 4),
        "max_loss_pct":   round(max_loss_pct, 4),
    }


def _empty_indicator_stat(name: str) -> dict:
    """오류 발생 시 기본값(0) 통계 딕셔너리를 반환한다."""
    return {
        "name":           name,
        "signal_count":   0,
        "long_signals":   0,
        "short_signals":  0,
        "hit_count":      0,
        "hit_rate":       0.0,
        "avg_return_pct": 0.0,
        "max_win_pct":    0.0,
        "max_loss_pct":   0.0,
    }


def _read_cache(symbol: str, horizon_h: int, lookback: int) -> dict | None:
    """auto_backtest_cache 테이블에서 유효한(1시간 이내) 캐시를 조회한다.

    테이블이 없으면 None을 반환한다.
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT result_json FROM auto_backtest_cache "
                "WHERE symbol=? AND horizon_h=? AND lookback=? "
                "AND datetime(computed_at) > datetime('now', '-1 hour') "
                "ORDER BY computed_at DESC LIMIT 1",
                (symbol, horizon_h, lookback),
            ).fetchone()
        if row is None:
            return None
        # from_cache는 캐시된 JSON에 포함하지 않으므로 파싱 후 설정
        data = json.loads(row[0])
        data["from_cache"] = True
        return data
    except sqlite3.OperationalError:
        # 테이블 미존재 등 → 캐시 없음으로 처리
        return None


def _write_cache(symbol: str, horizon_h: int, lookback: int, result: dict) -> None:
    """백테스트 결과를 auto_backtest_cache 테이블에 INSERT한다.

    만료된 기존 행을 삭제 후 INSERT한다. 테이블이 없으면 조용히 무시한다.
    """
    try:
        # from_cache 키는 캐시에 저장하지 않음 (로드 시 동적으로 설정)
        result_to_cache = {k: v for k, v in result.items() if k != "from_cache"}
        result_json   = json.dumps(result_to_cache, ensure_ascii=False)
        computed_at   = result.get("computed_at", datetime.now(timezone.utc).isoformat())
        with get_db() as conn:
            # 만료된 기존 캐시 행 삭제
            conn.execute(
                "DELETE FROM auto_backtest_cache "
                "WHERE symbol=? AND horizon_h=? AND lookback=? "
                "AND datetime(computed_at) <= datetime('now', '-1 hour')",
                (symbol, horizon_h, lookback),
            )
            conn.execute(
                "INSERT INTO auto_backtest_cache "
                "(symbol, horizon_h, lookback, computed_at, result_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (symbol, horizon_h, lookback, computed_at, result_json),
            )
    except sqlite3.OperationalError as e:
        logger.warning("auto_backtest_cache 쓰기 실패 (테이블 미존재?): %s", e)


def _compute_backtest(symbol: str, horizon_h: int, data: dict) -> dict:
    """CPU-bound 백테스트 계산을 수행하는 동기 함수.

    13개 지표 시그널을 순차적으로 실행하고 결과 딕셔너리를 반환한다.
    """
    closes  = data["closes"]
    highs   = data["highs"]
    lows    = data["lows"]
    volumes = data["volumes"]

    # 13개 지표 시그널 함수 디스패치
    signal_calls = [
        ("RSI",     lambda: signals_rsi(closes)),
        ("MACD",    lambda: signals_macd(closes)),
        ("볼린저밴드", lambda: signals_bollinger(closes)),
        ("MA",      lambda: signals_ma(closes)),
        ("EMA",     lambda: signals_ema(closes)),
        ("거래량",   lambda: signals_volume(closes, volumes)),
        ("지지/저항", lambda: signals_support_resistance(closes, highs, lows)),
        ("피보나치",  lambda: signals_fibonacci(closes, highs, lows)),
        ("일목균형표", lambda: signals_ichimoku(closes, highs, lows)),
        ("스토캐스틱", lambda: signals_stochastic(closes, highs, lows)),
        ("추세선",   lambda: signals_trendline(closes)),
        ("ADX",     lambda: signals_adx(closes, highs, lows)),
        ("ATR",     lambda: signals_atr(closes, highs, lows)),
    ]

    indicators: list[dict] = []
    for name, fn in signal_calls:
        try:
            signals = fn()
            stat = _calc_indicator_stats(name, signals, closes, horizon_h)
        except Exception as exc:
            logger.warning("지표 '%s' 계산 중 오류 발생: %s", name, exc, exc_info=True)
            stat = _empty_indicator_stat(name)
        indicators.append(stat)

    computed_at = datetime.now(timezone.utc).isoformat()
    return {
        "symbol":        symbol,
        "horizon_h":     horizon_h,
        "lookback_bars": data["bar_count"],
        "computed_at":   computed_at,
        "from_cache":    False,
        "indicators":    indicators,
    }


# ---------------------------------------------------------------------------
# 메인 함수
# ---------------------------------------------------------------------------

async def run_backtest(symbol: str, horizon_h: int = 24, lookback: int = 500) -> dict:
    """백테스트를 실행하고 13개 지표의 적중률 통계를 반환한다.

    캐시가 유효하면 DB 연산 없이 캐시 결과를 반환한다.
    블로킹 DB/CPU 작업은 run_in_executor를 통해 이벤트 루프를 차단하지 않는다.

    Args:
        symbol:    거래 심볼 (예: "BTCUSDT")
        horizon_h: 시그널 이후 평가할 봉 수 (기본 24)
        lookback:  사용할 최대 봉 수 (기본 500)

    Returns:
        indicators 리스트를 포함한 백테스트 결과 딕셔너리

    Raises:
        ValueError: OHLCV 데이터가 60봉 미만이거나 존재하지 않을 때
    """
    loop = asyncio.get_running_loop()

    # 1) 캐시 조회 (blocking DB)
    cached = await loop.run_in_executor(None, _read_cache, symbol, horizon_h, lookback)
    if cached is not None:
        return cached

    # 2) OHLCV 로드 (blocking DB)
    data = await loop.run_in_executor(None, _load_ohlcv, symbol, lookback)
    if data is None:
        raise ValueError(f"데이터 부족: {symbol} 최소 60봉 필요")

    # 3) 동기 백테스트 계산 (CPU-bound)
    result = await loop.run_in_executor(None, _compute_backtest, symbol, horizon_h, data)

    # 4) 캐시 저장 (blocking DB)
    await loop.run_in_executor(None, _write_cache, symbol, horizon_h, lookback, result)

    return result


# ---------------------------------------------------------------------------
# 직접 실행 테스트 (데이터가 있을 때만)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    async def _main() -> None:
        try:
            result = await run_backtest("BTCUSDT", horizon_h=24)
            print(f"symbol      : {result['symbol']}")
            print(f"horizon_h   : {result['horizon_h']}")
            print(f"lookback_bars: {result['lookback_bars']}")
            print(f"computed_at : {result['computed_at']}")
            print(f"from_cache  : {result['from_cache']}")
            print(f"지표 수      : {len(result['indicators'])}")
            for ind in result["indicators"]:
                print(
                    f"  {ind['name']:12s} | "
                    f"시그널={ind['signal_count']:3d} "
                    f"(L={ind['long_signals']}/S={ind['short_signals']}) | "
                    f"적중={ind['hit_rate']:5.1f}% | "
                    f"평균수익={ind['avg_return_pct']:+.4f}%"
                )
        except ValueError as e:
            print(f"[INFO] {e}")

    asyncio.run(_main())
