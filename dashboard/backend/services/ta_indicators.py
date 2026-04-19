"""
기술적 분석 지표 계산 엔진
OHLCV numpy 배열로부터 13개 기술적 지표를 계산하고 Long/Short 시그널을 생성한다.
"""

import numpy as np

# ---------------------------------------------------------------------------
# 내부 계산 헬퍼 (private)
# ---------------------------------------------------------------------------

def _ema_array(values: np.ndarray, period: int) -> np.ndarray:
    """벡터화된 EMA 계산. 유효한 값은 period-1 인덱스부터 시작한다."""
    result = np.full(len(values), np.nan)
    if len(values) < period:
        return result
    # 첫 번째 EMA 값 = 단순 평균
    result[period - 1] = np.mean(values[:period])
    k = 2.0 / (period + 1)
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI 계산. 유효한 값은 period 인덱스부터 시작한다."""
    result = np.full(len(closes), np.nan)
    if len(closes) < period + 1:
        return result
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    # 초기 평균 (단순 평균)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - 100.0 / (1.0 + rs)
    # Wilder 스무딩
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - 100.0 / (1.0 + rs)
    return result


def _macd(closes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """MACD 12/26/9 계산. (macd_line, signal_line) 반환."""
    ema12 = _ema_array(closes, 12)
    ema26 = _ema_array(closes, 26)
    macd_line = ema12 - ema26
    # signal은 macd_line의 EMA9; nan이 섞인 구간은 무시
    signal_line = np.full(len(closes), np.nan)
    first_valid = 26 - 1  # ema26이 처음 유효한 인덱스
    valid_macd = macd_line[first_valid:]
    ema9_of_macd = _ema_array(valid_macd, 9)
    signal_line[first_valid:] = ema9_of_macd
    return macd_line, signal_line


def _bollinger(closes: np.ndarray, period: int = 20, num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """볼린저 밴드 계산. (upper, mid, lower) 반환."""
    n = len(closes)
    upper = np.full(n, np.nan)
    mid = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = closes[i - period + 1: i + 1]
        m = np.mean(window)
        s = np.std(window, ddof=0)
        mid[i] = m
        upper[i] = m + num_std * s
        lower[i] = m - num_std * s
    return upper, mid, lower


def _stochastic(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    k: int = 14,
    d: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """%K, %D 계산."""
    n = len(closes)
    pct_k = np.full(n, np.nan)
    for i in range(k - 1, n):
        h = np.max(highs[i - k + 1: i + 1])
        l = np.min(lows[i - k + 1: i + 1])
        if h == l:
            pct_k[i] = 50.0
        else:
            pct_k[i] = 100.0 * (closes[i] - l) / (h - l)
    # %D = %K의 d-기간 단순 이동 평균
    pct_d = np.full(n, np.nan)
    for i in range(k - 1 + d - 1, n):
        window = pct_k[i - d + 1: i + 1]
        if not np.any(np.isnan(window)):
            pct_d[i] = np.mean(window)
    return pct_k, pct_d


def _adx(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ADX, +DI, -DI 계산. (adx, plus_di, minus_di) 반환."""
    n = len(closes)
    adx_arr = np.full(n, np.nan)
    plus_di_arr = np.full(n, np.nan)
    minus_di_arr = np.full(n, np.nan)
    if n < period + 1:
        return adx_arr, plus_di_arr, minus_di_arr

    # True Range, +DM, -DM
    tr = np.full(n, np.nan)
    plus_dm = np.full(n, np.nan)
    minus_dm = np.full(n, np.nan)
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    # Wilder 스무딩 (초기값 = 합계)
    atr_sm = np.full(n, np.nan)
    pdm_sm = np.full(n, np.nan)
    mdm_sm = np.full(n, np.nan)
    atr_sm[period] = np.sum(tr[1: period + 1])
    pdm_sm[period] = np.sum(plus_dm[1: period + 1])
    mdm_sm[period] = np.sum(minus_dm[1: period + 1])
    for i in range(period + 1, n):
        atr_sm[i] = atr_sm[i - 1] - atr_sm[i - 1] / period + tr[i]
        pdm_sm[i] = pdm_sm[i - 1] - pdm_sm[i - 1] / period + plus_dm[i]
        mdm_sm[i] = mdm_sm[i - 1] - mdm_sm[i - 1] / period + minus_dm[i]

    # +DI, -DI
    for i in range(period, n):
        if atr_sm[i] == 0:
            continue
        plus_di_arr[i] = 100.0 * pdm_sm[i] / atr_sm[i]
        minus_di_arr[i] = 100.0 * mdm_sm[i] / atr_sm[i]

    # DX → ADX (Wilder 스무딩)
    dx = np.full(n, np.nan)
    for i in range(period, n):
        pd = plus_di_arr[i]
        md = minus_di_arr[i]
        if np.isnan(pd) or np.isnan(md):
            continue
        dsum = pd + md
        if dsum == 0:
            dx[i] = 0.0
        else:
            dx[i] = 100.0 * abs(pd - md) / dsum

    # ADX 초기값: dx[period] ~ dx[2*period-1] (총 period개) 의 단순 평균
    first_adx = 2 * period - 1  # ADX 최초 유효 인덱스
    if first_adx < n:
        valid_dx = dx[period: first_adx + 1]
        valid_dx_clean = valid_dx[~np.isnan(valid_dx)]
        if len(valid_dx_clean) == period:
            adx_arr[first_adx] = np.mean(valid_dx_clean)
            for i in range(first_adx + 1, n):
                if not np.isnan(dx[i]) and not np.isnan(adx_arr[i - 1]):
                    adx_arr[i] = (adx_arr[i - 1] * (period - 1) + dx[i]) / period

    return adx_arr, plus_di_arr, minus_di_arr


def _atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """ATR 계산 (Wilder 스무딩)."""
    n = len(closes)
    atr_arr = np.full(n, np.nan)
    if n < period + 1:
        return atr_arr
    tr = np.full(n, np.nan)
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    # 초기 ATR = 단순 평균
    atr_arr[period] = np.mean(tr[1: period + 1])
    for i in range(period + 1, n):
        atr_arr[i] = (atr_arr[i - 1] * (period - 1) + tr[i]) / period
    return atr_arr


# ---------------------------------------------------------------------------
# 시그널 생성 함수 (public)
# ---------------------------------------------------------------------------

def signals_rsi(closes: np.ndarray) -> list[tuple[int, str]]:
    """RSI 14. RSI < 30 → 'long', RSI > 70 → 'short'."""
    MIN_LEN = 15
    if len(closes) < MIN_LEN:
        return []
    rsi = _rsi(closes, 14)
    result: list[tuple[int, str]] = []
    for i in range(1, len(closes)):
        if np.isnan(rsi[i]):
            continue
        # < 30 진입 시점 (처음 떨어지는 바)
        if rsi[i] < 30 and (np.isnan(rsi[i - 1]) or rsi[i - 1] >= 30):
            result.append((i, "long"))
        # > 70 진입 시점
        elif rsi[i] > 70 and (np.isnan(rsi[i - 1]) or rsi[i - 1] <= 70):
            result.append((i, "short"))
    return result


def signals_macd(closes: np.ndarray) -> list[tuple[int, str]]:
    """MACD 12/26/9. MACD 라인이 Signal 라인을 상향돌파 → 'long', 하향돌파 → 'short'."""
    MIN_LEN = 35
    if len(closes) < MIN_LEN:
        return []
    macd_line, signal_line = _macd(closes)
    result: list[tuple[int, str]] = []
    for i in range(1, len(closes)):
        if np.isnan(macd_line[i]) or np.isnan(signal_line[i]):
            continue
        if np.isnan(macd_line[i - 1]) or np.isnan(signal_line[i - 1]):
            continue
        prev_diff = macd_line[i - 1] - signal_line[i - 1]
        curr_diff = macd_line[i] - signal_line[i]
        if prev_diff <= 0 and curr_diff > 0:
            result.append((i, "long"))
        elif prev_diff >= 0 and curr_diff < 0:
            result.append((i, "short"))
    return result


def signals_bollinger(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """볼린저 밴드 20/2σ. close < lower → 'long', close > upper → 'short'."""
    MIN_LEN = 21
    if len(closes) < MIN_LEN:
        return []
    upper, mid, lower = _bollinger(closes, 20, 2.0)
    result: list[tuple[int, str]] = []
    for i in range(len(closes)):
        if np.isnan(upper[i]) or np.isnan(lower[i]):
            continue
        if closes[i] < lower[i]:
            result.append((i, "long"))
        elif closes[i] > upper[i]:
            result.append((i, "short"))
    return result


def signals_ma(closes: np.ndarray) -> list[tuple[int, str]]:
    """MA 20. 종가가 MA를 상향돌파 → 'long', 하향돌파 → 'short'."""
    MIN_LEN = 21
    if len(closes) < MIN_LEN:
        return []
    n = len(closes)
    ma = np.full(n, np.nan)
    for i in range(19, n):
        ma[i] = np.mean(closes[i - 19: i + 1])
    result: list[tuple[int, str]] = []
    for i in range(1, n):
        if np.isnan(ma[i]) or np.isnan(ma[i - 1]):
            continue
        prev_above = closes[i - 1] > ma[i - 1]
        curr_above = closes[i] > ma[i]
        if not prev_above and curr_above:
            result.append((i, "long"))
        elif prev_above and not curr_above:
            result.append((i, "short"))
    return result


def signals_ema(closes: np.ndarray) -> list[tuple[int, str]]:
    """EMA 20. 종가가 EMA를 상향돌파 → 'long', 하향돌파 → 'short'."""
    MIN_LEN = 21
    if len(closes) < MIN_LEN:
        return []
    ema = _ema_array(closes, 20)
    result: list[tuple[int, str]] = []
    for i in range(1, len(closes)):
        if np.isnan(ema[i]) or np.isnan(ema[i - 1]):
            continue
        prev_above = closes[i - 1] > ema[i - 1]
        curr_above = closes[i] > ema[i]
        if not prev_above and curr_above:
            result.append((i, "long"))
        elif prev_above and not curr_above:
            result.append((i, "short"))
    return result


def signals_volume(closes: np.ndarray, volumes: np.ndarray) -> list[tuple[int, str]]:
    """볼륨 스파이크(20기간 평균 × 2). 스파이크 + 상승 → 'long', 스파이크 + 하락 → 'short'."""
    MIN_LEN = 21
    if len(closes) < MIN_LEN:
        return []
    n = len(closes)
    result: list[tuple[int, str]] = []
    for i in range(20, n):
        vol_avg = np.mean(volumes[i - 20: i])  # 현재 바 제외한 20개
        spike = volumes[i] > vol_avg * 2
        if not spike:
            continue
        if closes[i] > closes[i - 1]:
            result.append((i, "long"))
        elif closes[i] < closes[i - 1]:
            result.append((i, "short"))
    return result


def signals_support_resistance(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """지지/저항. 20바 롤링 고점/저점 기준 ±0.5% 이내 터치 시 시그널."""
    MIN_LEN = 21
    if len(closes) < MIN_LEN:
        return []
    n = len(closes)
    result: list[tuple[int, str]] = []
    for i in range(20, n):
        # 현재 바 이전 20개 바 기준 (현재 바 제외)
        resistance = np.max(highs[i - 20: i])
        support = np.min(lows[i - 20: i])
        c = closes[i]
        pc = closes[i - 1]
        tol_sup = support * 0.005
        tol_res = resistance * 0.005
        # 지지선 반등: 종가가 지지선 ±0.5% 이내 AND 이전 종가 > 지지선 (위에서 접근)
        if abs(c - support) <= tol_sup and pc > support:
            result.append((i, "long"))
        # 저항선 거절: 종가가 저항선 ±0.5% 이내 AND 이전 종가 < 저항선 (아래서 접근)
        elif abs(c - resistance) <= tol_res and pc < resistance:
            result.append((i, "short"))
    return result


def signals_fibonacci(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """피보나치 되돌림. 50바 롤링 스윙. 61.8% 레벨(0.382 상승) 근접 시 시그널."""
    MIN_LEN = 51
    if len(closes) < MIN_LEN:
        return []
    n = len(closes)
    result: list[tuple[int, str]] = []
    for i in range(50, n):
        swing_high = np.max(highs[i - 50: i])
        swing_low = np.min(lows[i - 50: i])
        diff = swing_high - swing_low
        if diff == 0:
            continue
        # 상승 추세 지지 레벨 (38.2% 되돌림 = 61.8% 상승 유지)
        level_up = swing_low + diff * 0.382
        # 하락 추세 저항 레벨 (61.8% 되돌림)
        level_dn = swing_high - diff * 0.382
        c = closes[i]
        pc = closes[i - 1]
        tol_up = level_up * 0.005
        tol_dn = level_dn * 0.005
        if abs(c - level_up) <= tol_up and c > pc:
            result.append((i, "long"))
        elif abs(c - level_dn) <= tol_dn and c < pc:
            result.append((i, "short"))
    return result


def signals_ichimoku(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """일목균형표. 텐칸(9), 기준(26), 선행스팬A/B(26/52). 구름 위/아래 + 텐칸/기준 교차 시그널."""
    MIN_LEN = 53
    if len(closes) < MIN_LEN:
        return []
    n = len(closes)

    def mid_val(h: np.ndarray, l: np.ndarray, start: int, end: int) -> float:
        return (np.max(h[start:end]) + np.min(l[start:end])) / 2.0

    result: list[tuple[int, str]] = []
    for i in range(52, n):
        tenkan = mid_val(highs, lows, i - 8, i + 1)       # 9기간
        kijun = mid_val(highs, lows, i - 25, i + 1)       # 26기간
        # 선행스팬은 현재 기준 26 미래로 이동되지만,
        # 신호 판단 시에는 현재 시점의 cloud (과거 26기간 선행스팬)를 사용
        # 여기서는 과거 26바 시점의 선행스팬 A/B를 현재 cloud로 간주
        span_a = (mid_val(highs, lows, i - 34, i - 25) + mid_val(highs, lows, i - 51, i - 25)) / 2.0 \
            if i >= 51 else np.nan
        span_b = mid_val(highs, lows, i - 51, i - 25) if i >= 51 else np.nan
        if np.isnan(span_a) or np.isnan(span_b):
            continue
        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)
        c = closes[i]
        if c > cloud_top and tenkan > kijun:
            result.append((i, "long"))
        elif c < cloud_bot and tenkan < kijun:
            result.append((i, "short"))
    return result


def signals_stochastic(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """스토캐스틱 14/3/3. %K < 20 + %K가 %D를 상향돌파 → 'long'. %K > 80 + 하향돌파 → 'short'."""
    MIN_LEN = 17
    if len(closes) < MIN_LEN:
        return []
    pct_k, pct_d = _stochastic(highs, lows, closes, k=14, d=3)
    result: list[tuple[int, str]] = []
    for i in range(1, len(closes)):
        if np.isnan(pct_k[i]) or np.isnan(pct_d[i]):
            continue
        if np.isnan(pct_k[i - 1]) or np.isnan(pct_d[i - 1]):
            continue
        # %K가 %D를 상향돌파 (이전: %K <= %D, 현재: %K > %D)
        crossed_up = pct_k[i - 1] <= pct_d[i - 1] and pct_k[i] > pct_d[i]
        # %K가 %D를 하향돌파
        crossed_dn = pct_k[i - 1] >= pct_d[i - 1] and pct_k[i] < pct_d[i]
        if pct_k[i] < 20 and crossed_up:
            result.append((i, "long"))
        elif pct_k[i] > 80 and crossed_dn:
            result.append((i, "short"))
    return result


def signals_trendline(closes: np.ndarray) -> list[tuple[int, str]]:
    """트렌드라인 (선형 회귀 20바). 기울기 > 0 + 종가 > 회귀값 → 'long'. 반대 → 'short'."""
    MIN_LEN = 20
    if len(closes) < MIN_LEN:
        return []
    n = len(closes)
    x = np.arange(20, dtype=float)
    result: list[tuple[int, str]] = []
    for i in range(19, n):
        window = closes[i - 19: i + 1]
        coeffs = np.polyfit(x, window, 1)
        slope = coeffs[0]
        lr_value = coeffs[0] * 19 + coeffs[1]  # 마지막 바의 회귀값
        if slope > 0 and closes[i] > lr_value:
            result.append((i, "long"))
        elif slope < 0 and closes[i] < lr_value:
            result.append((i, "short"))
    return result


def signals_adx(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """ADX 14. ADX > 25 AND +DI > -DI → 'long'. ADX > 25 AND -DI > +DI → 'short'."""
    MIN_LEN = 29
    if len(closes) < MIN_LEN:
        return []
    adx_arr, plus_di, minus_di = _adx(highs, lows, closes, 14)
    result: list[tuple[int, str]] = []
    for i in range(len(closes)):
        if np.isnan(adx_arr[i]) or np.isnan(plus_di[i]) or np.isnan(minus_di[i]):
            continue
        if adx_arr[i] > 25:
            if plus_di[i] > minus_di[i]:
                result.append((i, "long"))
            elif minus_di[i] > plus_di[i]:
                result.append((i, "short"))
    return result


def signals_atr(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
) -> list[tuple[int, str]]:
    """ATR 14. ATR 스파이크(20기간 평균 × 1.5) 시 방향 기반 시그널."""
    MIN_LEN = 15
    if len(closes) < MIN_LEN:
        return []
    atr = _atr(highs, lows, closes, 14)
    n = len(closes)
    result: list[tuple[int, str]] = []
    for i in range(20, n):  # 20기간 평균 계산 위해 최소 20 필요
        window = atr[i - 20: i]
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            continue
        atr_mean = np.mean(valid)
        if np.isnan(atr[i]):
            continue
        spike = atr[i] > atr_mean * 1.5
        if not spike:
            continue
        if closes[i] > closes[i - 1]:
            result.append((i, "long"))
        elif closes[i] < closes[i - 1]:
            result.append((i, "short"))
    return result


# ---------------------------------------------------------------------------
# 샌티티 테스트 (단독 실행 시)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import random

    random.seed(42)
    np.random.seed(42)

    N = 200  # 충분한 바 수

    # 합성 OHLCV 생성 (랜덤 워크 기반)
    closes = np.cumsum(np.random.randn(N) * 10) + 10000.0
    highs = closes + np.abs(np.random.randn(N) * 5)
    lows = closes - np.abs(np.random.randn(N) * 5)
    opens = closes + np.random.randn(N) * 3
    volumes = np.abs(np.random.randn(N) * 1000) + 5000.0

    # 각 함수 테스트
    tests = [
        ("signals_rsi",               signals_rsi(closes)),
        ("signals_macd",              signals_macd(closes)),
        ("signals_bollinger",         signals_bollinger(closes, highs, lows)),
        ("signals_ma",                signals_ma(closes)),
        ("signals_ema",               signals_ema(closes)),
        ("signals_volume",            signals_volume(closes, volumes)),
        ("signals_support_resistance",signals_support_resistance(closes, highs, lows)),
        ("signals_fibonacci",         signals_fibonacci(closes, highs, lows)),
        ("signals_ichimoku",          signals_ichimoku(closes, highs, lows)),
        ("signals_stochastic",        signals_stochastic(closes, highs, lows)),
        ("signals_trendline",         signals_trendline(closes)),
        ("signals_adx",               signals_adx(closes, highs, lows)),
        ("signals_atr",               signals_atr(closes, highs, lows)),
    ]

    all_ok = True
    for name, result in tests:
        # 반환값이 list인지 확인
        assert isinstance(result, list), f"{name}: list가 아님 ({type(result)})"
        # 각 원소가 (int, str) 튜플인지 확인
        for item in result:
            assert isinstance(item, tuple) and len(item) == 2, f"{name}: 원소 형식 오류 {item}"
            assert isinstance(item[0], (int, np.integer)), f"{name}: 인덱스가 int가 아님 {item}"
            assert item[1] in ("long", "short"), f"{name}: 방향 값 오류 {item}"
        print(f"  OK  {name}: {len(result)}개 시그널")

    # 최소 데이터 미달 시 빈 리스트 반환 확인
    short_closes = np.array([100.0] * 10)
    short_highs = short_closes + 1
    short_lows = short_closes - 1
    short_vols = np.ones(10) * 1000
    assert signals_rsi(short_closes) == [], "RSI 최소 데이터 미달 시 [] 반환 실패"
    assert signals_macd(short_closes) == [], "MACD 최소 데이터 미달 시 [] 반환 실패"
    assert signals_bollinger(short_closes, short_highs, short_lows) == [], "BB 최소 데이터 미달 시 [] 반환 실패"
    print("  OK  최소 데이터 미달 케이스 모두 [] 반환")

    print("\n모든 sanity check 통과!")
