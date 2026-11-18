"""일목균형표 전체 요소 계산 테스트 (선형 캔들로 손계산 값 고정)."""
from dashboard.backend.services.learning_indicators import ichimoku, ichimoku_state

DAY = 86_400_000
C = [{"open_time": i * DAY, "high": i, "low": i, "close": i, "open": i, "volume": 1} for i in range(100)]


def test_ichimoku_linear():
    ich = ichimoku(C, DAY)
    row = {r["time"]: r for r in ich}
    assert row[60 * DAY]["tenkan"] == 56.0  # (60+52)/2
    assert row[60 * DAY]["kijun"] == 47.5  # (60+35)/2
    assert row[86 * DAY]["senkou_a"] == (56.0 + 47.5) / 2  # 60번 봉 값이 26봉 앞으로
    assert row[86 * DAY]["senkou_b"] == (60 + 9) / 2  # 52봉 고저 중간
    assert row[34 * DAY]["chikou"] == 60  # 60번 종가가 26봉 뒤로
    assert len(ich) == 100 + 26 and ich[-1]["time"] == 125 * DAY and ich[-1]["tenkan"] is None


def test_state_above_cloud_golden():
    st = ichimoku_state(C, ichimoku(C, DAY))
    assert st == {"cloud_position": "above", "tk_cross": "golden", "chikou": "above", "future_cloud": "bullish"}
