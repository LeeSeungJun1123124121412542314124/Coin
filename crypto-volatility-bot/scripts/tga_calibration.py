"""TGA 4주 변화 알림 임계치 캘리브레이션 (일회성).

계획: docs/plans/tga-liquidity-signal-2026-07-04.md §2-D

절차:
  1. FRED WTREGEN(재무부 일반계정, 백만$) 5년 수집 → 일봉 ffill
  2. non-overlapping 4주 블록 |Δ| 분포에서 후보 임계치 3개(상위 10/15/20%) 산출
  3. 각 후보 T에 대해 실제 히스테리시스 상태머신(T·0.7T·방향전환 재발화)을
     일봉 Δ4W 시계열에 시뮬레이션 → 연평균 발화 횟수 산출
  4. 연 4~8회 구간에 드는 값을 추천

실행: crypto-volatility-bot/.venv/Scripts/python.exe crypto-volatility-bot/scripts/tga_calibration.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd
from dotenv import load_dotenv

# 프로젝트 루트/봇 경로 등록 (app.macro import 용)
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOT_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _BOT_ROOT)
load_dotenv(os.path.join(_BOT_ROOT, ".env"))

from app.macro.collectors import _fetch_fred  # noqa: E402

_HYSTERESIS = 0.7  # 리셋 배수 (production과 동일)
_TARGET_MIN, _TARGET_MAX = 4, 8  # 목표 연평균 발화 횟수


def simulate_fires(delta_4w: pd.Series, T: float, reset_ratio: float = _HYSTERESIS) -> int:
    """일봉 Δ4W 시계열에 3상태 히스테리시스 상태머신 시뮬 → 발화 횟수.

    상태: neutral / above_positive / above_negative
    발화: neutral→above_±, above_+↔above_− (방향전환). |Δ|<reset_ratio*T 시 무발화 리셋.
    """
    state = "neutral"
    fires = 0
    reset = reset_ratio * T
    for d in delta_4w.dropna():
        if state == "neutral":
            if d >= T:
                state, fires = "above_positive", fires + 1
            elif d <= -T:
                state, fires = "above_negative", fires + 1
        elif state == "above_positive":
            if d <= -T:
                state, fires = "above_negative", fires + 1
            elif abs(d) < reset:
                state = "neutral"
        else:  # above_negative
            if d >= T:
                state, fires = "above_positive", fires + 1
            elif abs(d) < reset:
                state = "neutral"
    return fires


def _load_series() -> pd.Series:
    """WTREGEN 시계열 — TGA_CSV(로컬 Avast 우회용 PowerShell 수집분) 있으면 파일, 없으면 FRED."""
    csv = os.getenv("TGA_CSV")
    if csv and os.path.exists(csv):
        df = pd.read_csv(csv)
        s = pd.Series(df["value"].astype(float).values, index=pd.to_datetime(df["date"]))
        return s.sort_index()
    return _fetch_fred("WTREGEN", start="2021-01-01")


def main() -> None:
    # 1. 수집 — 5년(부채한도 2023 재적립 이벤트 포함 위해 2021-01부터)
    tga = _load_series()
    if tga.empty:
        raise SystemExit("WTREGEN 수집 실패 (빈 시계열)")
    daily = tga.resample("D").ffill()
    span_days = (daily.index[-1] - daily.index[0]).days
    years = span_days / 365.25

    def bil(m: float) -> str:                    # 백만$ → $B 표기
        return f"${m/1000:,.0f}B"

    delta_4w = daily.diff(28)
    print(f"데이터 범위 : {daily.index[0].date()} ~ {daily.index[-1].date()} ({years:.1f}년)")
    print(f"WTREGEN 단위: 백만$  (최근값 {daily.iloc[-1]:,.0f} = {bil(daily.iloc[-1])})")
    print(f"일봉 Δ4W 범위: {delta_4w.min():,.0f} ~ {delta_4w.max():,.0f} 백만$")
    print()

    # 2. non-overlapping 4주 블록 |Δ| 분위수 (자기상관 보정 후보)
    block_delta_abs = daily.iloc[::28].diff().abs().dropna()
    print(f"non-overlapping 4주 블록 수: {len(block_delta_abs)}")
    print("블록 |Δ| 분위수:")
    for q in (0.90, 0.85, 0.80, 0.70, 0.60, 0.50):
        print(f"  상위{int((1-q)*100):>2}% (q{q:.2f}): {block_delta_abs.quantile(q):>10,.0f} 백만$  ({bil(block_delta_abs.quantile(q))})")
    print()

    # 3. 실제 알림 신호(일봉 Δ4W)에 히스테리시스 상태머신 시뮬 → 연평균 발화
    #    분위 후보가 과소발화라 넓은 절대 임계 그리드로 목표(연 4~8회) 탐색
    print(f"{'임계 T':>10}{'총 발화':>8}{'연평균':>8}  판정")
    grid = list(range(80_000, 270_000, 10_000))  # $80B ~ $260B
    target_hits = []
    for T in grid:
        fires = simulate_fires(delta_4w, T)
        per_year = fires / years
        ok = _TARGET_MIN <= per_year <= _TARGET_MAX
        mark = "✅ 목표" if ok else ("↑과다" if per_year > _TARGET_MAX else "↓과소")
        if ok:
            target_hits.append((T, per_year))
        print(f"{bil(T):>10}{fires:>8}{per_year:>8.1f}  {mark}")
    print()

    if target_hits:
        # 목표 구간의 중앙값 T 추천
        mid = target_hits[len(target_hits) // 2]
        print(f"▶ 추천 임계 T = {mid[0]:,} 백만$ ({bil(mid[0])}), 연 {mid[1]:.1f}회 발화")
        print(f"  (목표 구간 전체: {bil(target_hits[0][0])} ~ {bil(target_hits[-1][0])})")
    else:
        print("▶ 그리드 내 목표(연 4~8회) 구간 없음 — 목표 범위 재검토 필요")


if __name__ == "__main__":
    main()
