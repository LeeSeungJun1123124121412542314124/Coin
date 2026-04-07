"""Tests for outlier_detector indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analyzers.indicators.outlier_detector import detect


def _make_df(n=50, close_val=100.0, open_offset=0.0):
    close = np.ones(n) * close_val
    open_ = np.ones(n) * (close_val + open_offset)
    return pd.DataFrame({
        "open": open_, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.ones(n) * 1000,
    })


def _normal_atr():
    return {"atr": 1.0, "atr_prev_avg": 1.0}


def _normal_bb(percent_b=0.5):
    return {
        "upper": 105.0, "middle": 100.0, "lower": 95.0,
        "bandwidth": 0.1, "bandwidth_prev": 0.1,
        "percent_b": percent_b, "squeeze": False, "expanding": False,
        "price_above_middle": True, "middle_line_break": None,
    }


def _normal_volume():
    return {"volume": 1000.0, "volume_avg": 1000.0, "volume_ratio": 1.0, "spike": False}


def _default_config():
    return {"atr_spike_multiplier": 2.0, "single_candle_pct": 5.0}


def test_returns_required_keys():
    result = detect(
        atr_data=_normal_atr(),
        bb_data=_normal_bb(),
        volume_data=_normal_volume(),
        price_df=_make_df(),
        config=_default_config(),
    )
    for key in ("is_outlier", "is_critical", "severity", "alerts", "single_candle_pct"):
        assert key in result


def test_normal_data_severity_zero():
    result = detect(
        atr_data=_normal_atr(),
        bb_data=_normal_bb(),
        volume_data=_normal_volume(),
        price_df=_make_df(),
        config=_default_config(),
    )
    assert result["severity"] == 0
    assert result["is_outlier"] is False
    assert result["is_critical"] is False


def test_atr_spike_triggers_alert():
    """ATR 3x prev avg (> 2x multiplier) → alert."""
    atr_data = {"atr": 3.0, "atr_prev_avg": 1.0}
    result = detect(
        atr_data=atr_data,
        bb_data=_normal_bb(),
        volume_data=_normal_volume(),
        price_df=_make_df(),
        config=_default_config(),
    )
    assert result["severity"] >= 1
    assert result["is_outlier"] is True
    assert any("ATR" in a for a in result["alerts"])


def test_volume_spike_triggers_alert():
    """Volume spike flag → alert."""
    volume_data = {"volume": 5000.0, "volume_avg": 1000.0, "volume_ratio": 5.0, "spike": True}
    result = detect(
        atr_data=_normal_atr(),
        bb_data=_normal_bb(),
        volume_data=volume_data,
        price_df=_make_df(),
        config=_default_config(),
    )
    assert result["is_outlier"] is True
    assert any("거래량" in a for a in result["alerts"])


def test_bb_extreme_upper_deviation():
    """%B > 2.0 → extreme upper deviation alert."""
    result = detect(
        atr_data=_normal_atr(),
        bb_data=_normal_bb(percent_b=2.5),
        volume_data=_normal_volume(),
        price_df=_make_df(),
        config=_default_config(),
    )
    assert result["is_outlier"] is True
    assert any("%B" in a for a in result["alerts"])


def test_bb_extreme_lower_deviation():
    """%B < -1.0 → extreme lower deviation alert."""
    result = detect(
        atr_data=_normal_atr(),
        bb_data=_normal_bb(percent_b=-1.5),
        volume_data=_normal_volume(),
        price_df=_make_df(),
        config=_default_config(),
    )
    assert result["is_outlier"] is True


def test_single_candle_large_move():
    """Single candle 10% move (> 5% threshold) → alert."""
    # open=100, close=110 → 10% move
    df = _make_df(open_offset=10.0)  # open = close + 10
    result = detect(
        atr_data=_normal_atr(),
        bb_data=_normal_bb(),
        volume_data=_normal_volume(),
        price_df=df,
        config=_default_config(),
    )
    assert result["single_candle_pct"] > 5.0
    assert result["is_outlier"] is True


def test_severity_2_when_two_alerts():
    """Two alerts → severity=2, is_critical=True."""
    atr_data = {"atr": 3.0, "atr_prev_avg": 1.0}  # ATR spike alert
    volume_data = {"volume": 5000.0, "volume_avg": 1000.0, "volume_ratio": 5.0, "spike": True}  # volume alert
    result = detect(
        atr_data=atr_data,
        bb_data=_normal_bb(),
        volume_data=volume_data,
        price_df=_make_df(),
        config=_default_config(),
    )
    assert result["severity"] == 2
    assert result["is_critical"] is True


def test_severity_capped_at_2():
    """Even with 3+ alerts, severity max is 2."""
    atr_data = {"atr": 5.0, "atr_prev_avg": 1.0}
    volume_data = {"volume": 10000.0, "volume_avg": 1000.0, "volume_ratio": 10.0, "spike": True}
    df = _make_df(open_offset=20.0)
    result = detect(
        atr_data=atr_data,
        bb_data=_normal_bb(percent_b=3.0),
        volume_data=volume_data,
        price_df=df,
        config=_default_config(),
    )
    assert result["severity"] <= 2
