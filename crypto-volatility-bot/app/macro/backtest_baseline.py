"""8년 복합 백테스트의 순수 계산부 — 팩터 프레임 조립 + 베이스라인 적중률.

계획: docs/plans/spf-phase2-3-calibration-reweight-2026-07-05.md 0단계.
scripts/composite_history.py(수집·저장)가 사용하고, 3단계(재가중 전후 비교)와
2단계(z 구간별 보정 곡선)가 같은 계산을 재사용한다.

방법론은 docs/RESEARCH_direction-signals.md §2와 동일:
IC = 순위의 피어슨(rank pearson), 중립밴드는 direction_composite._NEUTRAL_BAND.
"""

from __future__ import annotations

import pandas as pd

from app.macro.direction_composite import _NEUTRAL_BAND, build_factors, compute_composite


def rank_ic(signal: pd.Series, target: pd.Series) -> float | None:
    """순위 피어슨 IC (scipy 부재 환경용 스피어만 대용). 유효 페어 < 30이면 None."""
    df = pd.concat([signal, target], axis=1, keys=["s", "t"]).dropna()
    if len(df) < 30:
        return None
    return float(df["s"].rank().corr(df["t"].rank()))


def build_history_frame(sources: dict[str, pd.Series]) -> pd.DataFrame:
    """원시 소스 → 9팩터 변환 시계열 + composite + close 단일 프레임."""
    factors = build_factors(**sources)
    composite = compute_composite(factors)
    frame = pd.DataFrame(factors)
    frame["composite"] = composite
    frame["close"] = sources["close"]
    return frame


def forward_hit_stats(
    composite: pd.Series,
    close: pd.Series,
    horizons: tuple[int, ...] = (7, 14, 30, 60),
    neutral_band: float = _NEUTRAL_BAND,
) -> dict[str, dict]:
    """호라이즌별 방향 적중률·IC — 동등가중 베이스라인 (3단계 비교 기준).

    적중 정의: composite ≥ +band → forward 수익 > 0 이면 적중,
              composite ≤ −band → forward 수익 < 0 이면 적중.
    |composite| < band 는 중립으로 집계에서 제외(카운트만 보고).
    """
    out: dict[str, dict] = {}
    for horizon in horizons:
        fwd = close.shift(-horizon) / close - 1
        df = pd.concat([composite.rename("z"), fwd.rename("fwd")], axis=1).dropna()
        long_mask = df["z"] >= neutral_band
        short_mask = df["z"] <= -neutral_band
        neutral_mask = ~long_mask & ~short_mask

        long_hits = (df.loc[long_mask, "fwd"] > 0)
        short_hits = (df.loc[short_mask, "fwd"] < 0)
        n_long, n_short = int(long_mask.sum()), int(short_mask.sum())
        n_directional = n_long + n_short

        def pct(hits: pd.Series, n: int) -> float | None:
            return round(float(hits.sum()) / n * 100.0, 1) if n else None

        out[str(horizon)] = {
            "n_long": n_long,
            "n_short": n_short,
            "n_neutral": int(neutral_mask.sum()),
            "hit_long": pct(long_hits, n_long),
            "hit_short": pct(short_hits, n_short),
            "hit_directional": pct(
                pd.concat([long_hits, short_hits]), n_directional
            ),
            "baseline_up_rate": round(float((df["fwd"] > 0).mean()) * 100.0, 1),
            "ic": (lambda v: round(v, 3) if v is not None else None)(
                rank_ic(df["z"], df["fwd"])
            ),
        }
    return out
