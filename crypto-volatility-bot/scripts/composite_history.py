"""8년(2018~) 복합 방향모델 백테스트 파이프라인 — SPF 0단계.

계획: docs/plans/spf-phase2-3-calibration-reweight-2026-07-05.md 0단계.
3단계(재가중)·2단계(확률 보정)의 공통 재료를 재현 가능하게 생성한다.

절차:
  1. 원시 소스 수집 (Binance BTC 일봉 2018~ + FRED + CoinMetrics)
     → data/composite_sources.csv 저장
  2. 9팩터 변환 + composite z 조립 → data/composite_history.csv 저장
  3. 동등가중 베이스라인 적중률·IC (7/14/30/60일)
     → data/composite_baseline.json 저장 + 콘솔 출력

실행: crypto-volatility-bot/.venv/Scripts/python.exe crypto-volatility-bot/scripts/composite_history.py
오프라인 재계산(수집 생략): ... composite_history.py --from-csv data/composite_sources.csv
로컬 Avast TLS 차단 시: MACRO_CA_BUNDLE 환경변수로 CA 번들 지정 (collectors와 동일)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

import pandas as pd
from dotenv import load_dotenv

# 프로젝트 루트/봇 경로 등록 (app.macro import 용)
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOT_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _BOT_ROOT)
load_dotenv(os.path.join(_BOT_ROOT, ".env"))

from app.macro.backtest_baseline import build_history_frame, forward_hit_stats  # noqa: E402
from app.macro.collectors import _fetch_coinmetrics, _fetch_daily, _fetch_fred  # noqa: E402

_START = "2018-01-01"
_DATA_DIR = os.path.join(_BOT_ROOT, "data")
_SOURCE_COLS = ["close", "net_liquidity", "tga", "dxy", "ust10y", "vix", "mvrv", "active_addr"]


def fetch_full_sources() -> dict[str, pd.Series]:
    """2018-01-01부터 전체 히스토리 수집 — collectors.fetch_sources의 풀레인지 판.

    (ETH/SOL은 9팩터에 불참이라 제외. tga는 리더보드 지표 소스라 포함.)
    """
    days = (date.today() - date.fromisoformat(_START)).days + 30
    close = _fetch_daily("BTCUSDT", days=days)
    if close.empty:
        raise RuntimeError("BTC 일봉 수집 실패")
    idx = close.index

    def R(s: pd.Series) -> pd.Series:
        return s.reindex(idx, method="ffill")

    walcl, tga, rrp = _fetch_fred("WALCL"), _fetch_fred("WTREGEN"), _fetch_fred("RRPONTSYD")
    tga_d = R(tga)
    return {
        "close": close,
        "net_liquidity": R(walcl) - tga_d - R(rrp) * 1000,
        "tga": tga_d,
        "dxy": R(_fetch_fred("DTWEXBGS")),
        "ust10y": R(_fetch_fred("DGS10")),
        "vix": R(_fetch_fred("VIXCLS")),
        "mvrv": R(_fetch_coinmetrics("CapMVRVCur")),
        "active_addr": R(_fetch_coinmetrics("AdrActCnt")),
    }


def load_sources_csv(path: str) -> dict[str, pd.Series]:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return {c: df[c] for c in _SOURCE_COLS}


def main() -> None:
    parser = argparse.ArgumentParser(description="8년 복합 백테스트 파이프라인 (SPF 0단계)")
    parser.add_argument("--from-csv", help="저장된 sources CSV로 오프라인 재계산 (수집 생략)")
    args = parser.parse_args()

    if args.from_csv:
        sources = load_sources_csv(args.from_csv)
        print(f"오프라인 모드: {args.from_csv}")
    else:
        sources = fetch_full_sources()
        os.makedirs(_DATA_DIR, exist_ok=True)
        sources_path = os.path.join(_DATA_DIR, "composite_sources.csv")
        pd.DataFrame({k: sources[k] for k in _SOURCE_COLS}).to_csv(sources_path)
        print(f"소스 저장: {sources_path}")

    frame = build_history_frame(sources)
    span = f"{frame.index[0].date()} ~ {frame.index[-1].date()}"
    print(f"데이터 범위: {span} ({len(frame)}일, composite 유효 {frame['composite'].notna().sum()}일)")

    os.makedirs(_DATA_DIR, exist_ok=True)
    history_path = os.path.join(_DATA_DIR, "composite_history.csv")
    frame.to_csv(history_path)
    print(f"팩터·복합 저장: {history_path}")

    stats = forward_hit_stats(frame["composite"], frame["close"])
    report = {
        "generated_for": "SPF 0단계 — 동등가중 베이스라인 (3단계 재가중 비교 기준)",
        "span": span,
        "rows": len(frame),
        "horizons": stats,
    }
    report_path = os.path.join(_DATA_DIR, "composite_baseline.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"베이스라인 저장: {report_path}\n")

    print(f"{'H':>4} {'강세n':>6} {'약세n':>6} {'중립n':>6} {'강세적중':>8} {'약세적중':>8} {'방향적중':>8} {'기준상승률':>10} {'IC':>7}")
    for horizon, h in stats.items():
        print(
            f"{horizon:>4} {h['n_long']:>6} {h['n_short']:>6} {h['n_neutral']:>6}"
            f" {h['hit_long'] if h['hit_long'] is not None else '-':>8}"
            f" {h['hit_short'] if h['hit_short'] is not None else '-':>8}"
            f" {h['hit_directional'] if h['hit_directional'] is not None else '-':>8}"
            f" {h['baseline_up_rate']:>10} {h['ic'] if h['ic'] is not None else '-':>7}"
        )


if __name__ == "__main__":
    main()
