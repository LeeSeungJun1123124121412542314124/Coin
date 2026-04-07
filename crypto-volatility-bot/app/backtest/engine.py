"""Backtest engine — sliding-window historical replay of TechnicalAnalyzer.

Usage:
    engine = BacktestEngine(config_path="config/technical.yaml", window_size=100)
    result = engine.run(df, evaluation_bars=10, signal_threshold=4)
    print(result.metrics)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.analyzers.technical_analyzer import TechnicalAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class BacktestSignal:
    """A single signal emitted during backtest replay."""

    bar_index: int
    score: float
    signal: str           # HIGH / MEDIUM / LOW
    direction: str        # BEARISH / BULLISH / NEUTRAL
    points: float
    sideways_active: bool
    deduplicated: bool = False  # True when suppressed by min_signal_gap cooldown


@dataclass
class BacktestResult:
    """Aggregate results from a backtest run."""

    signals: list[BacktestSignal]
    metrics: dict[str, float]
    parameters: dict[str, Any]


class BacktestEngine:
    """Replay TechnicalAnalyzer over historical OHLCV data with a sliding window."""

    def __init__(
        self,
        config_path: str | None = None,
        window_size: int = 100,
    ) -> None:
        self._analyzer = TechnicalAnalyzer(config_path)
        self._window = window_size

    def run(
        self,
        df: pd.DataFrame,
        evaluation_bars: int = 10,
        signal_threshold: float = 4.0,
        min_signal_gap: int | None = None,
    ) -> BacktestResult:
        """Slide the window over df and collect signals + hit-rate metrics.

        Args:
            df: Full historical OHLCV DataFrame.
            evaluation_bars: How many bars ahead to evaluate direction prediction.
            signal_threshold: Minimum points to count as an "active" signal.
            min_signal_gap: Minimum bars between two active signals to avoid
                counting the same event multiple times in overlapping windows.
                Defaults to ``max(evaluation_bars, window_size // 5)``.

        Returns:
            BacktestResult with per-signal data and aggregate metrics.
        """
        n = len(df)
        if n < self._window + evaluation_bars:
            return BacktestResult(
                signals=[],
                metrics={"error": "insufficient_data"},
                parameters={"window_size": self._window, "evaluation_bars": evaluation_bars},
            )

        _gap = min_signal_gap if min_signal_gap is not None else max(evaluation_bars, self._window // 5)
        last_active_bar: int = -_gap - 1  # allow first signal immediately

        signals: list[BacktestSignal] = []
        correct_direction = 0
        total_evaluated = 0

        for end in range(self._window, n - evaluation_bars):
            window_df = df.iloc[end - self._window : end].reset_index(drop=True)
            try:
                result = self._analyzer.analyze(window_df)
            except Exception as e:
                logger.debug("윈도우 %d 분석 실패 (건너뜀): %s", end, e)
                continue

            details = result.details
            points = details.get("points", 0.0)
            direction = details.get("direction", "NEUTRAL")
            sideways_active = details.get("sideways", {}).get("active", False)

            is_active = points >= signal_threshold
            is_dedup = is_active and (end - last_active_bar) < _gap

            sig = BacktestSignal(
                bar_index=end,
                score=result.score,
                signal=result.signal,
                direction=direction,
                points=float(points),
                sideways_active=sideways_active,
                deduplicated=is_dedup,
            )
            signals.append(sig)

            if is_active and not is_dedup:
                last_active_bar = end

            # Evaluate direction prediction (only unique active signals)
            if is_active and not is_dedup and direction != "NEUTRAL":
                future_close = float(df.iloc[end + evaluation_bars - 1]["close"])
                current_close = float(df.iloc[end - 1]["close"])
                actual_move = "BULLISH" if future_close > current_close else "BEARISH"
                if actual_move == direction:
                    correct_direction += 1
                total_evaluated += 1

        # Aggregate metrics
        total_signals = len(signals)
        active_signals = [s for s in signals if s.points >= signal_threshold]
        unique_active = [s for s in active_signals if not s.deduplicated]
        high_signals = sum(1 for s in signals if s.signal == "HIGH")
        medium_signals = sum(1 for s in signals if s.signal == "MEDIUM")
        avg_score = sum(s.score for s in signals) / total_signals if total_signals > 0 else 0.0
        avg_points = sum(s.points for s in signals) / total_signals if total_signals > 0 else 0.0
        hit_rate = correct_direction / total_evaluated if total_evaluated > 0 else 0.0
        signals_per_bar = len(active_signals) / (n - self._window - evaluation_bars) if (n - self._window - evaluation_bars) > 0 else 0.0

        metrics: dict[str, float] = {
            "total_bars": float(n),
            "total_signals": float(total_signals),
            "active_signals": float(len(active_signals)),
            "unique_active_signals": float(len(unique_active)),
            "high_signals": float(high_signals),
            "medium_signals": float(medium_signals),
            "avg_score": avg_score,
            "avg_points": avg_points,
            "hit_rate": hit_rate,
            "total_evaluated": float(total_evaluated),
            "correct_direction": float(correct_direction),
            "signals_per_bar": signals_per_bar,
        }

        return BacktestResult(
            signals=signals,
            metrics=metrics,
            parameters={
                "window_size": self._window,
                "evaluation_bars": evaluation_bars,
                "signal_threshold": signal_threshold,
            },
        )
