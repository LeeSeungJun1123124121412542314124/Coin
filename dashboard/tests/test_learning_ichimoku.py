"""일목균형표 전체 요소 계산 테스트 (선형 캔들로 손계산 값 고정)."""
from datetime import datetime, timezone

import pytest

from dashboard.backend.services.learning_indicators import ichimoku, ichimoku_state, next_open_time

DAY = 86_400_000
C = [{"open_time": i * DAY, "high": i, "low": i, "close": i, "open": i, "volume": 1} for i in range(100)]


def test_ichimoku_linear():
    ich = ichimoku(C, "1d")
    row = {r["time"]: r for r in ich}
    assert row[60 * DAY]["tenkan"] == 56.0  # (60+52)/2
    assert row[60 * DAY]["kijun"] == 47.5  # (60+35)/2
    assert row[86 * DAY]["senkou_a"] == (56.0 + 47.5) / 2  # 60번 봉 값이 26봉 앞으로
    assert row[86 * DAY]["senkou_b"] == (60 + 9) / 2  # 52봉 고저 중간
    assert row[34 * DAY]["chikou"] == 60  # 60번 종가가 26봉 뒤로
    assert len(ich) == 100 + 26 and ich[-1]["time"] == 125 * DAY and ich[-1]["tenkan"] is None


def test_state_above_cloud_golden():
    st = ichimoku_state(C, ichimoku(C, "1d"))
    assert st == {"cloud_position": "above", "tk_cross": "golden", "chikou": "above", "future_cloud": "bullish"}


def test_state_insufficient_data_returns_none():
    c = C[:20]
    st = ichimoku_state(c, ichimoku(c, "1d"))
    assert st == {"cloud_position": None, "tk_cross": None, "chikou": None, "future_cloud": None}


def _ms(y: int, m: int, d: int = 1) -> int:
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


def test_next_open_time():
    assert next_open_time(_ms(2024, 1), "1M") == _ms(2024, 2)
    assert next_open_time(_ms(2024, 2), "1M") == _ms(2024, 3)
    assert next_open_time(_ms(2024, 12), "1M") == _ms(2025, 1)
    assert next_open_time(0, "1w") == 604_800_000
    assert next_open_time(0, "1h") == 3_600_000
    with pytest.raises(ValueError):
        next_open_time(0, "15m")


def test_ichimoku_monthly_future_times():
    candles = []
    for i in range(60):  # 마지막 봉 open_time = 2024-11-01
        y, m = divmod(2024 * 12 + 10 - (59 - i), 12)
        t = _ms(y, m + 1)
        candles.append({"open_time": t, "high": 2, "low": 1, "close": 1.5, "open": 1, "volume": 1})
    ich = ichimoku(candles, "1M")
    assert ich[60]["time"] == _ms(2024, 12)
    assert ich[60 + 25]["time"] == _ms(2027, 1)
