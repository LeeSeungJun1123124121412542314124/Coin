"""
종합 자동 백테스트 서비스

매크로 점수(research_analyzer)와 기술적 점수(RSI/MACD/BB/ADX)를 합산한
롱/숏 독립 점수를 기반으로 진입/청산 신호를 생성하고
지정 기간 내 백테스트 결과를 반환한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

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
    long_threshold: float = 70.0
    short_threshold: float = 70.0
    leverage: float = 1.0
    position_size_pct: float = 100.0
    score_exit_buffer: float = 15.0

    def __post_init__(self):
        if self.stop_loss_pct <= 0:
            raise ValueError(f"stop_loss_pct must be > 0, got {self.stop_loss_pct}")
        if self.take_profit_pct <= 0:
            raise ValueError(f"take_profit_pct must be > 0, got {self.take_profit_pct}")
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be > 0, got {self.initial_capital}")
        if self.leverage <= 0 or self.leverage > 100:
            raise ValueError(f"leverage must be > 0 and <= 100, got {self.leverage}")
        if self.position_size_pct <= 0 or self.position_size_pct > 100:
            raise ValueError(
                f"position_size_pct must be > 0 and <= 100, got {self.position_size_pct}"
            )
        if not (0 < self.long_threshold <= 100):
            raise ValueError(f"long_threshold must be in (0, 100], got {self.long_threshold}")
        if not (0 < self.short_threshold <= 100):
            raise ValueError(f"short_threshold must be in (0, 100], got {self.short_threshold}")
        if not (0 <= self.score_exit_buffer < 100):
            raise ValueError("score_exit_buffer는 0 이상 100 미만이어야 합니다")
        if self.score_exit_buffer >= self.long_threshold:
            raise ValueError(
                f"score_exit_buffer({self.score_exit_buffer})는 long_threshold({self.long_threshold})보다 작아야 합니다"
            )
        if self.score_exit_buffer >= self.short_threshold:
            raise ValueError(
                f"score_exit_buffer({self.score_exit_buffer})는 short_threshold({self.short_threshold})보다 작아야 합니다"
            )


# ---------------------------------------------------------------------------
# 심볼 포맷 변환 (BTCUSDT → BTC/USDT)
# ---------------------------------------------------------------------------

_KNOWN_QUOTES = ["USDT", "BTC", "ETH", "BNB", "BUSD", "USDC"]

# 인터벌별 밀리초 단위 캔들 크기
_INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


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
        elif rsi_val < 50:
            scores.append(60.0)   # 중립~약한 강세
        elif rsi_val < 70:
            scores.append(45.0)   # 중립
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


def calc_tech_bearish_score(details: dict) -> float:
    """RSI·MACD·BB·ADX 세부 지표를 약세(숏) 점수로 변환 후 평균을 반환한다.

    유효한 지표만 포함해 평균을 구한다. 모두 None이면 50 반환.
    """
    scores: list[float] = []

    # RSI: 과매수일수록 숏 강세
    rsi_val = details.get("rsi")
    if rsi_val is not None:
        if rsi_val > 70:
            scores.append(85.0)   # 과매수 = 숏 강세
        elif rsi_val > 55:
            scores.append(65.0)
        elif rsi_val > 40:
            scores.append(45.0)
        else:
            scores.append(20.0)   # 과매도

    # MACD: 하향 확대일수록 숏 강세
    macd_val = details.get("macd")
    if macd_val is not None:
        hist = macd_val.get("histogram")
        prev_hist = macd_val.get("prev_histogram")
        if hist is not None and prev_hist is not None:
            if hist < 0 and hist < prev_hist:
                scores.append(75.0)   # 하향 확대
            elif hist < 0:
                scores.append(55.0)
            elif hist > 0 and hist > prev_hist:
                scores.append(25.0)   # 상향 확대
            else:
                scores.append(45.0)

    # BB %B: 상단 근접일수록 숏 강세
    bb_val = details.get("bb")
    if bb_val is not None:
        if bb_val > 0.8:
            scores.append(80.0)   # 상단 근접 = 숏 강세
        elif bb_val > 0.6:
            scores.append(60.0)
        elif bb_val > 0.4:
            scores.append(45.0)
        else:
            scores.append(25.0)

    # ADX: 강한 하락 추세일수록 숏 강세
    adx_val = details.get("adx")
    if adx_val is not None:
        adx = adx_val.get("adx", 0.0)
        plus_di = adx_val.get("plus_di", 0.0)
        minus_di = adx_val.get("minus_di", 0.0)
        if adx > 25 and minus_di > plus_di:
            scores.append(70.0)   # 강한 하락 추세
        elif adx > 25:
            scores.append(30.0)
        else:
            scores.append(50.0)

    if not scores:
        return 50.0
    return sum(scores) / len(scores)


def calc_long_score(macro_bullish: float, tech_details: dict) -> float:
    """매크로 강세 + 기술적 강세 점수를 4:6 비율로 합산해 롱 점수를 반환한다."""
    return macro_bullish * 0.4 + calc_tech_bullish_score(tech_details) * 0.6


def calc_short_score(macro_bullish: float, tech_details: dict) -> float:
    """매크로 약세 + 기술적 약세 점수를 4:6 비율로 합산해 숏 점수를 반환한다."""
    macro_bearish = 100.0 - macro_bullish
    return macro_bearish * 0.4 + calc_tech_bearish_score(tech_details) * 0.6


# ---------------------------------------------------------------------------
# 전체 DataFrame 기반 지표 일괄 계산 (O(n) 최적화)
# ---------------------------------------------------------------------------

def _safe_float(series: pd.Series, loc) -> float | None:
    """Series에서 loc 위치 값을 안전하게 float으로 반환한다."""
    try:
        val = series.loc[loc]
        return None if pd.isna(val) else float(val)
    except Exception:
        return None


def _compute_all_indicators(full_df: pd.DataFrame) -> dict[str, pd.Series]:
    """전체 OHLCV DataFrame에 대해 RSI/MACD/BB/ADX를 한 번만 계산 후 Series 반환."""
    close = full_df["close"]
    high = full_df["high"]
    low = full_df["low"]

    # RSI (14 period)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi_series = 100 - 100 / (1 + rs)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram_series = macd_line - signal_line
    prev_histogram_series = histogram_series.shift(1)

    # BB %B (20 period)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = sma20 + 2 * std20
    lower_band = sma20 - 2 * std20
    band_width = upper - lower_band
    bb_series = (close - lower_band) / band_width.replace(0, float("nan"))

    # ADX (14 period)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
    plus_di_series = 100 * plus_dm.rolling(14).mean() / atr
    minus_di_series = 100 * minus_dm.rolling(14).mean() / atr
    dx = (
        (plus_di_series - minus_di_series).abs()
        / (plus_di_series + minus_di_series).replace(0, float("nan"))
        * 100
    )
    adx_series = dx.rolling(14).mean()

    return {
        "rsi": rsi_series,
        "histogram": histogram_series,
        "prev_histogram": prev_histogram_series,
        "bb": bb_series,
        "adx": adx_series,
        "plus_di": plus_di_series,
        "minus_di": minus_di_series,
    }


# ---------------------------------------------------------------------------
# 동기 내부 함수 (스레드 풀에서 실행)
# ---------------------------------------------------------------------------

def _fetch_ohlcv(params: CompositeBacktestParams) -> pd.DataFrame | None:
    """DataCollector._get_exchange()로 OHLCV를 수집해 datetime 인덱스 DataFrame을 반환한다.

    start_date 기준 워밍업 200봉 이전 시점부터 since를 계산해 요청한다.
    """
    try:
        from app.data.data_collector import DataCollector

        collector = DataCollector()
        exchange = collector._get_exchange()
        ccxt_symbol = _normalize_symbol(params.symbol)

        # since 계산: start_date에서 워밍업(200봉) 만큼 앞선 시점
        if params.start_date:
            start_ts_ms = int(pd.Timestamp(params.start_date, tz="UTC").timestamp() * 1000)
            warmup_ms = 200 * _INTERVAL_MS.get(params.interval, 3_600_000)
            since = start_ts_ms - warmup_ms
        else:
            since = None

        raw = exchange.fetch_ohlcv(
            ccxt_symbol,
            timeframe=params.interval,
            limit=2000,
            since=since,
        )
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
    """동기 백테스트 루프. 스레드 풀에서 실행된다.

    롱/숏 독립 점수 시스템, Flip, 레버리지, 수수료, 강제청산을 지원한다.
    """

    FEE_RATE = 0.0006  # 0.06% 수수료

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

    # 전체 DataFrame 기준으로 지표 일괄 계산 (O(n), 루프 외부)
    indicator_series = _compute_all_indicators(full_df)

    initial_capital = params.initial_capital
    capital = initial_capital
    position: dict | None = None
    trades: list[dict] = []
    equity_curve: list[dict] = []
    liquidated = False

    total_candles = len(target_indices)

    for seq, idx in enumerate(target_indices):
        candle_row = full_df.iloc[idx]
        loc = full_df.index[idx]
        ts_str = loc.isoformat()
        close = float(candle_row["close"])
        high = float(candle_row["high"])
        low = float(candle_row["low"])

        # 인덱스 조회만으로 지표값 추출 (재계산 없음)
        details = {
            "rsi": _safe_float(indicator_series["rsi"], loc),
            "macd": {
                "histogram": _safe_float(indicator_series["histogram"], loc),
                "prev_histogram": _safe_float(indicator_series["prev_histogram"], loc),
            },
            "bb": _safe_float(indicator_series["bb"], loc),
            "adx": {
                "adx": _safe_float(indicator_series["adx"], loc),
                "plus_di": _safe_float(indicator_series["plus_di"], loc),
                "minus_di": _safe_float(indicator_series["minus_di"], loc),
            },
        }

        # 롱/숏 독립 점수 계산
        long_score = calc_long_score(macro_bullish, details)
        short_score = calc_short_score(macro_bullish, details)

        long_threshold = params.long_threshold
        short_threshold = params.short_threshold
        is_last = (seq == total_candles - 1)

        # 양쪽 동시 트리거 여부
        both_triggered = (long_score > long_threshold) and (short_score > short_threshold)

        if position is None:
            # ── 포지션 없을 때: 진입 판단 ──
            if both_triggered:
                # 양쪽 모두 트리거 → 관망
                pass
            elif long_score > long_threshold and macro_bullish >= 40:
                # 롱 진입 (bearish 매크로 = macro_bullish < 40 시 차단)
                size = params.position_size_pct / 100.0
                allocated = capital * size
                entry_fee = allocated * FEE_RATE
                capital -= entry_fee
                position = {
                    "direction": "long",
                    "entry_price": close,
                    "entry_timestamp": ts_str,
                    "allocated": allocated,
                    "long_score": long_score,
                    "short_score": short_score,
                }
                trades.append({
                    "type": "entry",
                    "direction": "long",
                    "timestamp": ts_str,
                    "price": close,
                    "pnl_pct": None,
                    "reason": None,
                    "long_score": round(long_score, 2),
                    "short_score": round(short_score, 2),
                })
            elif short_score > short_threshold:
                # 숏 진입
                size = params.position_size_pct / 100.0
                allocated = capital * size
                entry_fee = allocated * FEE_RATE
                capital -= entry_fee
                position = {
                    "direction": "short",
                    "entry_price": close,
                    "entry_timestamp": ts_str,
                    "allocated": allocated,
                    "long_score": long_score,
                    "short_score": short_score,
                }
                trades.append({
                    "type": "entry",
                    "direction": "short",
                    "timestamp": ts_str,
                    "price": close,
                    "pnl_pct": None,
                    "reason": None,
                    "long_score": round(long_score, 2),
                    "short_score": round(short_score, 2),
                })

        else:
            # ── 포지션 있을 때: 청산 판단 ──
            direction = position["direction"]
            entry = position["entry_price"]
            reason: str | None = None

            exit_price = close  # 기본값: 종가 체결

            # 1순위: 손절 (SL) — 저가/고가로 체크, SL 정확한 가격에 체결
            sl_pct = params.stop_loss_pct / 100
            tp_pct = params.take_profit_pct / 100

            if direction == "long":
                sl_price = entry * (1 - sl_pct)
                tp_price = entry * (1 + tp_pct)
                if low <= sl_price:
                    reason = "stop_loss"
                    exit_price = sl_price
                elif high >= tp_price:
                    reason = "take_profit"
                    exit_price = tp_price
            else:  # short
                sl_price = entry * (1 + sl_pct)
                tp_price = entry * (1 - tp_pct)
                if high >= sl_price:
                    reason = "stop_loss"
                    exit_price = sl_price
                elif low <= tp_price:
                    reason = "take_profit"
                    exit_price = tp_price

            # 3순위: Flip (반대 방향 신호 강함)
            if reason is None:
                if direction == "long" and short_score > short_threshold and not both_triggered:
                    reason = "flip"
                elif direction == "short" and long_score > long_threshold and not both_triggered:
                    reason = "flip"

            # 4순위: 점수 하락 (score_exit) — buffer만큼 여유 부여
            if reason is None:
                exit_long = long_threshold - params.score_exit_buffer
                exit_short = short_threshold - params.score_exit_buffer
                if direction == "long" and long_score <= exit_long:
                    reason = "score_exit"
                elif direction == "short" and short_score <= exit_short:
                    reason = "score_exit"

            # 5순위: 기간 종료
            if reason is None and is_last:
                reason = "period_end"

            if reason:
                # ── 청산 실행 ──
                if direction == "long":
                    raw_return = (exit_price - entry) / entry
                else:  # short
                    raw_return = (entry - exit_price) / entry

                pnl_pct = raw_return * params.leverage * 100

                # 포지션 allocated 기준으로 손익 및 청산 수수료 계산
                pos_allocated = position["allocated"]
                pnl_amount = pos_allocated * (pnl_pct / 100.0)
                exit_fee = pos_allocated * FEE_RATE
                capital += pnl_amount - exit_fee

                # 강제청산 확인
                if capital <= 0:
                    capital = 0.0
                    liquidated = True
                    trades.append({
                        "type": "exit",
                        "direction": direction,
                        "timestamp": ts_str,
                        "price": exit_price,
                        "pnl_pct": round(pnl_pct, 4),
                        "reason": "liquidated",
                        "long_score": round(long_score, 2),
                        "short_score": round(short_score, 2),
                    })
                    equity_curve.append({
                        "timestamp": ts_str,
                        "value": 0.0,
                    })
                    position = None
                    break

                trades.append({
                    "type": "exit",
                    "direction": direction,
                    "timestamp": ts_str,
                    "price": exit_price,
                    "pnl_pct": round(pnl_pct, 4),
                    "reason": reason,
                    "long_score": round(long_score, 2),
                    "short_score": round(short_score, 2),
                })

                position = None

                # ── Flip: 청산 후 반대 방향 즉시 진입 ──
                if reason == "flip":
                    new_dir = "short" if direction == "long" else "long"
                    # bearish 매크로면 long 방향으로 flip 차단
                    if new_dir == "long" and macro_bullish < 40:
                        pass  # flip 진입 없이 포지션 없는 상태로 종료
                    else:
                        size = params.position_size_pct / 100.0
                        new_allocated = capital * size
                        entry_fee = new_allocated * FEE_RATE
                        capital -= entry_fee
                        position = {
                            "direction": new_dir,
                            "entry_price": close,
                            "entry_timestamp": ts_str,
                            "allocated": new_allocated,
                            "long_score": long_score,
                            "short_score": short_score,
                        }
                        trades.append({
                            "type": "entry",
                            "direction": new_dir,
                            "timestamp": ts_str,
                            "price": close,
                            "pnl_pct": None,
                            "reason": None,
                            "long_score": round(long_score, 2),
                            "short_score": round(short_score, 2),
                        })

        # ── equity_curve 기록 ──
        if position is None:
            current_value = capital
        else:
            entry = position["entry_price"]
            dir_ = position["direction"]
            pos_allocated = position["allocated"]
            if dir_ == "long":
                unrealized_pnl = (close / entry - 1) * params.leverage
            else:  # short
                unrealized_pnl = (entry / close - 1) * params.leverage
            current_value = capital + pos_allocated * unrealized_pnl

        equity_curve.append({
            "timestamp": ts_str,
            "value": round(current_value, 4),
        })

    # MDD 계산
    peak = initial_capital
    max_drawdown = 0.0
    for point in equity_curve:
        val = point["value"]
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100 if peak > 0 else 0.0
        if dd < max_drawdown:
            max_drawdown = dd

    # 요약 통계
    sell_trades = [t for t in trades if t["type"] == "exit"]
    long_trades = [t for t in sell_trades if t["direction"] == "long"]
    short_trades = [t for t in sell_trades if t["direction"] == "short"]
    trade_count = len(sell_trades)
    winning_trades = len([t for t in sell_trades if (t["pnl_pct"] or 0) > 0])
    losing_trades = trade_count - winning_trades
    win_rate = winning_trades / trade_count if trade_count > 0 else 0.0
    total_return_pct = (capital - initial_capital) / initial_capital * 100

    return {
        "summary": {
            "total_return_pct": round(total_return_pct, 4),
            "win_rate": round(win_rate, 4),
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "long_trade_count": len(long_trades),
            "short_trade_count": len(short_trades),
            "max_drawdown_pct": round(max_drawdown, 4),
            "final_capital": round(capital, 4),
            "liquidated": liquidated,
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
    # 날짜 형식 사전 검증
    for date_field in (params.start_date, params.end_date):
        if date_field:
            try:
                pd.Timestamp(date_field)
            except Exception:
                return {"error": f"날짜 형식 오류: {date_field!r} (예: '2024-01-01')"}

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
            "long_threshold": params.long_threshold,
            "short_threshold": params.short_threshold,
            "leverage": params.leverage,
            "position_size_pct": params.position_size_pct,
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
            long_threshold=70.0,
            short_threshold=70.0,
            leverage=1.0,
            position_size_pct=100.0,
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
