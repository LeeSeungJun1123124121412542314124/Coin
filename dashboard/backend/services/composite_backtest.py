"""
종합 자동 백테스트 서비스

매크로 점수(research_analyzer)와 기술적 점수(RSI/MACD/BB/ADX)를 합산한
복합 점수(composite score)를 기반으로 매수/매도 신호를 생성하고
지정 기간 내 백테스트 결과를 반환한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class CompositeBacktestParams:
    symbol: str = "BTC/USDT"          # ccxt 포맷 (BTC/USDT)
    interval: str = "1h"              # "1h" | "4h" | "1d"
    start_date: str = ""              # "2024-01-01"
    end_date: str = ""                # "2024-06-30"
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 5.0
    initial_capital: float = 10000.0


# ---------------------------------------------------------------------------
# 심볼 포맷 변환 (BTCUSDT → BTC/USDT)
# ---------------------------------------------------------------------------

_KNOWN_QUOTES = ["USDT", "BTC", "ETH", "BNB", "BUSD", "USDC"]


def _normalize_symbol(symbol: str) -> str:
    """API 입력 심볼을 ccxt 포맷으로 변환.

    "BTCUSDT" → "BTC/USDT", "BTC/USDT" → "BTC/USDT" (그대로)
    """
    if "/" in symbol:
        return symbol.upper()
    s = symbol.upper()
    for quote in _KNOWN_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"
    # 변환 불가 시 그대로 반환
    return s


# ---------------------------------------------------------------------------
# 점수 계산 함수들
# ---------------------------------------------------------------------------

def calc_macro_bullish_score(level: str) -> float:
    """매크로 레벨 문자열을 강세 점수(0~100)로 변환한다."""
    return {
        "bullish": 80.0,
        "neutral": 55.0,
        "bearish": 35.0,
        "warning": 20.0,
        "critical": 10.0,
    }.get(level, 50.0)


def calc_tech_bullish_score(details: dict) -> float:
    """RSI·MACD·BB·ADX 세부 지표를 강세 점수로 변환 후 평균을 반환한다.

    details 구조:
      - "rsi": float or None
      - "macd": {"histogram": float, "prev_histogram": float} or None
      - "bb": float (0~1, %B) or None
      - "adx": {"adx": float, "plus_di": float, "minus_di": float} or None

    유효한 지표만 포함해 평균을 구한다. 모두 None이면 50 반환.
    """
    scores: list[float] = []

    # RSI
    rsi_val = details.get("rsi")
    if rsi_val is not None:
        if rsi_val < 30:
            scores.append(85.0)   # 과매도
        elif rsi_val < 45:
            scores.append(65.0)
        elif rsi_val < 60:
            scores.append(45.0)
        else:
            scores.append(20.0)   # 과매수

    # MACD
    macd_val = details.get("macd")
    if macd_val is not None:
        hist = macd_val.get("histogram")
        prev_hist = macd_val.get("prev_histogram")
        if hist is not None and prev_hist is not None:
            if hist > 0 and hist > prev_hist:
                scores.append(75.0)   # 상향 확대
            elif hist > 0:
                scores.append(55.0)
            elif hist < 0 and hist < prev_hist:
                scores.append(25.0)   # 하향 확대
            else:
                scores.append(45.0)

    # BB (%B, 0~1)
    bb_val = details.get("bb")
    if bb_val is not None:
        if bb_val < 0.2:
            scores.append(80.0)   # 하단 근접
        elif bb_val < 0.4:
            scores.append(60.0)
        elif bb_val < 0.6:
            scores.append(45.0)
        else:
            scores.append(25.0)   # 상단 근접

    # ADX
    adx_val = details.get("adx")
    if adx_val is not None:
        adx = adx_val.get("adx", 0.0)
        plus_di = adx_val.get("plus_di", 0.0)
        minus_di = adx_val.get("minus_di", 0.0)
        if adx > 25 and plus_di > minus_di:
            scores.append(70.0)   # 강한 상승 추세
        elif adx > 25:
            scores.append(30.0)   # 강한 하락 추세
        else:
            scores.append(50.0)   # 추세 약함

    if not scores:
        return 50.0
    return sum(scores) / len(scores)


def calc_composite(macro_bullish: float, tech_bullish: float) -> float:
    """매크로·기술적 강세 점수를 4:6 비율로 합산한다."""
    return macro_bullish * 0.4 + tech_bullish * 0.6


# ---------------------------------------------------------------------------
# 개별 지표 직접 계산 (window_df 기반)
# ---------------------------------------------------------------------------

def _compute_indicators(window_df: pd.DataFrame) -> dict:
    """RSI·MACD·BB·ADX를 직접 계산해 calc_tech_bullish_score용 details dict를 반환한다."""
    from app.analyzers.indicators import (  # noqa: WPS433
        adx as adx_mod,
        bollinger_bands as bb_mod,
        rsi as rsi_mod,
    )

    details: dict = {}

    # RSI
    try:
        rsi_result = rsi_mod.calculate(window_df)
        details["rsi"] = rsi_result.get("rsi")
    except Exception as exc:
        logger.debug("RSI 계산 실패: %s", exc)
        details["rsi"] = None

    # MACD — prev_histogram은 histogram 시리즈에서 직접 추출
    try:
        close = window_df["close"]
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        current_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2]) if len(histogram) >= 2 else current_hist
        details["macd"] = {
            "histogram": current_hist,
            "prev_histogram": prev_hist,
        }
    except Exception as exc:
        logger.debug("MACD 계산 실패: %s", exc)
        details["macd"] = None

    # BB (%B)
    try:
        bb_result = bb_mod.calculate(window_df)
        details["bb"] = bb_result.get("percent_b")
    except Exception as exc:
        logger.debug("BB 계산 실패: %s", exc)
        details["bb"] = None

    # ADX
    try:
        adx_result = adx_mod.calculate(window_df)
        details["adx"] = {
            "adx": adx_result.get("adx", 0.0),
            "plus_di": adx_result.get("plus_di", 0.0),
            "minus_di": adx_result.get("minus_di", 0.0),
        }
    except Exception as exc:
        logger.debug("ADX 계산 실패: %s", exc)
        details["adx"] = None

    return details


# ---------------------------------------------------------------------------
# 동기 내부 함수 (스레드 풀에서 실행)
# ---------------------------------------------------------------------------

def _fetch_ohlcv(params: CompositeBacktestParams) -> pd.DataFrame | None:
    """DataCollector._get_exchange()로 OHLCV를 수집해 datetime 인덱스 DataFrame을 반환한다.

    워밍업 200개 + 기간 내 캔들을 한 번에 요청한다.
    ccxt limit 제한(1000봉)을 고려해 충분한 limit으로 요청한다.
    """
    try:
        from app.data.data_collector import DataCollector

        collector = DataCollector()
        exchange = collector._get_exchange()
        ccxt_symbol = _normalize_symbol(params.symbol)

        # 넉넉한 limit으로 요청 (워밍업 200 + 백테스트 기간 + 여유)
        limit = 2000

        raw = exchange.fetch_ohlcv(ccxt_symbol, timeframe=params.interval, limit=limit)
        if not raw:
            logger.warning("OHLCV 데이터 없음: symbol=%s", ccxt_symbol)
            return None

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("datetime").drop(columns=["timestamp"])
        df = df.sort_index()
        return df

    except Exception as exc:
        logger.error("OHLCV 수집 실패: %s", exc, exc_info=True)
        return None


def _run_backtest_sync(
    full_df: pd.DataFrame,
    params: CompositeBacktestParams,
    macro_bullish: float,
) -> dict:
    """동기 백테스트 루프. 스레드 풀에서 실행된다."""

    # start_date / end_date 파싱
    start_ts = (
        pd.Timestamp(params.start_date, tz="UTC")
        if params.start_date
        else full_df.index[0]
    )
    end_ts = (
        pd.Timestamp(params.end_date, tz="UTC")
        if params.end_date
        else full_df.index[-1]
    )

    # 워밍업 최소 100개 캔들 보장
    warmup_min = 100

    # target 인덱스: start_ts ~ end_ts 범위 캔들
    target_mask = (full_df.index >= start_ts) & (full_df.index <= end_ts)
    target_indices = [i for i, v in enumerate(target_mask) if v]

    if not target_indices:
        return {"error": "지정 기간 내 데이터 없음 (start_date ~ end_date 범위 확인)"}

    # 첫 target 캔들 기준으로 최소 warmup_min개 선행 캔들 확보 여부 확인
    first_target_idx = target_indices[0]
    if first_target_idx < warmup_min:
        # 워밍업 부족 → target_indices 앞쪽 제거해 warmup_min 보장
        target_indices = [i for i in target_indices if i >= warmup_min]
        if not target_indices:
            return {"error": f"워밍업 캔들 부족: 최소 {warmup_min}개 선행 데이터 필요"}

    capital = params.initial_capital
    position: dict | None = None
    trades: list[dict] = []
    equity_curve: list[dict] = []

    for seq, idx in enumerate(target_indices):
        # 슬라이딩 윈도우 (현재 캔들 포함)
        window_df = full_df.iloc[: idx + 1]
        candle_row = full_df.iloc[idx]
        ts_str = full_df.index[idx].isoformat()
        close_price = float(candle_row["close"])

        # 기술적 지표 계산
        try:
            details = _compute_indicators(window_df)
        except Exception as exc:
            logger.warning("지표 계산 실패 (idx=%d): %s", idx, exc)
            details = {}

        tech_bullish = calc_tech_bullish_score(details)
        composite = calc_composite(macro_bullish, tech_bullish)

        is_last_candle = (seq == len(target_indices) - 1)

        if position is None:
            # 매수 조건: composite > 70
            if composite > 70:
                position = {
                    "entry_price": close_price,
                    "entry_timestamp": ts_str,
                    "composite_score": composite,
                }
                trades.append({
                    "type": "buy",
                    "timestamp": ts_str,
                    "price": close_price,
                    "pnl_pct": None,
                    "reason": None,
                    "composite_score": round(composite, 2),
                })
        else:
            # 매도 조건 확인 (우선순위: 손절 > 익절 > 시그널역전 > 기간종료)
            entry = position["entry_price"]
            reason: str | None = None

            if close_price <= entry * (1 - params.stop_loss_pct / 100):
                reason = "stop_loss"
            elif close_price >= entry * (1 + params.take_profit_pct / 100):
                reason = "take_profit"
            elif composite < 30:
                reason = "score_signal"
            elif is_last_candle:
                reason = "period_end"

            if reason:
                pnl_pct = (close_price - entry) / entry * 100
                capital *= (1 + pnl_pct / 100)
                trades.append({
                    "type": "sell",
                    "timestamp": ts_str,
                    "price": close_price,
                    "pnl_pct": round(pnl_pct, 4),
                    "reason": reason,
                    "composite_score": round(composite, 2),
                })
                position = None

        # equity_curve 기록
        if position is None:
            current_value = capital
        else:
            entry = position["entry_price"]
            current_value = capital * (close_price / entry)

        equity_curve.append({
            "timestamp": ts_str,
            "value": round(current_value, 4),
        })

    # MDD 계산
    peak = params.initial_capital
    max_drawdown = 0.0
    for point in equity_curve:
        val = point["value"]
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100
        if dd < max_drawdown:
            max_drawdown = dd

    # 요약 통계
    sell_trades = [t for t in trades if t["type"] == "sell"]
    trade_count = len(sell_trades)
    winning_trades = sum(1 for t in sell_trades if (t["pnl_pct"] or 0) > 0)
    losing_trades = trade_count - winning_trades
    win_rate = winning_trades / trade_count if trade_count > 0 else 0.0
    total_return_pct = (capital - params.initial_capital) / params.initial_capital * 100

    return {
        "summary": {
            "total_return_pct": round(total_return_pct, 4),
            "win_rate": round(win_rate, 4),
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "max_drawdown_pct": round(max_drawdown, 4),
            "final_capital": round(capital, 4),
        },
        "trades": trades,
        "equity_curve": equity_curve,
    }


# ---------------------------------------------------------------------------
# 메인 async 함수
# ---------------------------------------------------------------------------

async def run_composite_backtest(params: CompositeBacktestParams) -> dict:
    """종합 백테스트를 실행하고 결과 딕셔너리를 반환한다.

    Args:
        params: CompositeBacktestParams 인스턴스

    Returns:
        summary, trades, equity_curve, params 키를 포함한 결과 딕셔너리.
        오류 시 {"error": str} 반환 (예외 raise 금지).
    """
    loop = asyncio.get_running_loop()

    # 심볼 정규화
    ccxt_symbol = _normalize_symbol(params.symbol)

    # 1) 매크로 점수 조회
    try:
        from dashboard.backend.services.research_analyzer import _analyze_macro
        macro_result = await _analyze_macro()
        macro_level = macro_result.get("level", "neutral")
    except Exception as exc:
        logger.warning("매크로 분석 실패, neutral로 대체: %s", exc)
        macro_level = "neutral"

    macro_bullish = calc_macro_bullish_score(macro_level)

    # 2) OHLCV 데이터 수집 (스레드 풀)
    full_df = await loop.run_in_executor(None, _fetch_ohlcv, params)
    if full_df is None or full_df.empty:
        return {"error": f"OHLCV 데이터 수집 실패: symbol={ccxt_symbol}, interval={params.interval}"}

    if len(full_df) < 100:
        return {"error": f"데이터 부족: {len(full_df)}봉 (최소 100봉 필요)"}

    # 3~6) 백테스트 루프 (스레드 풀)
    result = await loop.run_in_executor(
        None, _run_backtest_sync, full_df, params, macro_bullish
    )

    if "error" in result:
        return result

    return {
        "summary": result["summary"],
        "trades": result["trades"],
        "equity_curve": result["equity_curve"],
        "params": {
            "symbol": ccxt_symbol,
            "interval": params.interval,
            "start_date": params.start_date,
            "end_date": params.end_date,
            "stop_loss_pct": params.stop_loss_pct,
            "take_profit_pct": params.take_profit_pct,
            "macro_level": macro_level,
            "macro_bullish_score": macro_bullish,
        },
    }


# ---------------------------------------------------------------------------
# 직접 실행 테스트
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    async def _main() -> None:
        p = CompositeBacktestParams(
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01",
            end_date="2024-01-31",
            stop_loss_pct=3.0,
            take_profit_pct=5.0,
            initial_capital=10000.0,
        )
        result = await run_composite_backtest(p)
        if "error" in result:
            print(f"[오류] {result['error']}")
            return

        s = result["summary"]
        print(f"총 수익률    : {s['total_return_pct']:+.2f}%")
        print(f"승률         : {s['win_rate']*100:.1f}%")
        print(f"거래 횟수    : {s['trade_count']}")
        print(f"MDD          : {s['max_drawdown_pct']:.2f}%")
        print(f"최종 자산    : {s['final_capital']:,.2f}")
        print(f"매크로 레벨  : {result['params']['macro_level']}")

    asyncio.run(_main())
