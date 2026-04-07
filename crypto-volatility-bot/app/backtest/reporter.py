"""Backtest reporter — text summary formatter for BacktestResult."""

from __future__ import annotations

from app.backtest.engine import BacktestResult


def format_report(result: BacktestResult, title: str = "Backtest Report") -> str:
    """Format a BacktestResult as a human-readable text summary.

    Args:
        result: BacktestResult from BacktestEngine.run().
        title: Report header title.

    Returns:
        Multi-line text report.
    """
    m = result.metrics
    p = result.parameters

    if "error" in m:
        return f"[{title}]\nError: {m['error']}"

    hit_pct = m.get("hit_rate", 0.0) * 100.0
    total_bars = int(m.get("total_bars", 0))
    total_signals = int(m.get("total_signals", 0))
    active_signals = int(m.get("active_signals", 0))
    high_signals = int(m.get("high_signals", 0))
    medium_signals = int(m.get("medium_signals", 0))
    avg_score = m.get("avg_score", 0.0)
    avg_points = m.get("avg_points", 0.0)
    total_evaluated = int(m.get("total_evaluated", 0))
    correct = int(m.get("correct_direction", 0))
    spb = m.get("signals_per_bar", 0.0)

    lines = [
        f"{'=' * 40}",
        f"  {title}",
        f"{'=' * 40}",
        f"  파라미터",
        f"    윈도우 크기:    {p['window_size']} 봉",
        f"    평가 구간:     {p['evaluation_bars']} 봉 후",
        f"    신호 임계값:   {p['signal_threshold']} 점",
        f"",
        f"  결과 요약",
        f"    전체 봉 수:    {total_bars}",
        f"    분석 슬롯:     {total_signals}",
        f"    활성 신호:     {active_signals}  (HIGH: {high_signals}, MEDIUM: {medium_signals})",
        f"    신호/봉 비율:  {spb:.4f}",
        f"",
        f"  점수",
        f"    평균 점수:     {avg_score:.1f}",
        f"    평균 포인트:   {avg_points:.2f}",
        f"",
        f"  방향 예측",
        f"    평가 신호 수:  {total_evaluated}",
        f"    적중:          {correct}",
        f"    적중률:        {hit_pct:.1f}%",
        f"{'=' * 40}",
    ]
    return "\n".join(lines)
