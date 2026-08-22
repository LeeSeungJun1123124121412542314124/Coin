"""SPF 복합 이력 스크립트의 재가중 비교 테스트."""

from __future__ import annotations

import sys
from builtins import open as real_open
from io import StringIO
from pathlib import Path

import pandas as pd

BOT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BOT_ROOT / "scripts"))

import composite_history  # noqa: E402


def test_main_parses_weights_json_and_prints_comparison(monkeypatch, capsys):
    source_path = "unused-sources.csv"
    weights_path = Path(__file__).parent / "fixtures" / "factor_weights.json"

    idx = pd.date_range("2020-01-01", periods=2)
    frame = pd.DataFrame({"composite": [0.2, 0.3], "close": [100.0, 101.0]}, index=idx)
    monkeypatch.setattr(composite_history, "load_sources_csv", lambda _path: {"close": frame["close"]})
    monkeypatch.setattr(composite_history, "build_history_frame", lambda _sources: frame)
    monkeypatch.setattr(composite_history, "build_factors", lambda **_sources: {"vix_level": frame["composite"]})
    monkeypatch.setattr(composite_history, "compute_composite", lambda _factors, weights=None: frame["composite"] * 2)
    monkeypatch.setattr(composite_history.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda *_args, **_kwargs: None)

    def fake_open(path, *args, **kwargs):
        if str(path).endswith("composite_baseline.json"):
            return StringIO()
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(composite_history, "open", fake_open, raising=False)
    calls = []

    def fake_stats(composite, _close):
        calls.append(composite)
        return {
            str(h): {
                "n_long": 1,
                "n_short": 1,
                "n_neutral": 0,
                "hit_long": 50.0,
                "hit_short": 50.0,
                "hit_directional": 50.0 + len(calls),
                "baseline_up_rate": 50.0,
                "ic": 0.1 * len(calls),
            }
            for h in (7, 14, 30, 60)
        }

    monkeypatch.setattr(composite_history, "forward_hit_stats", fake_stats)
    monkeypatch.setattr(
        sys,
        "argv",
        ["composite_history.py", "--from-csv", str(source_path), "--weights-json", str(weights_path)],
    )

    composite_history.main()

    output = capsys.readouterr().out
    assert len(calls) == 2
    for horizon in (7, 14, 30, 60):
        assert f"H{horizon}" in output
    assert "동등가중" in output
    assert "재가중" in output
