"""선물 청산가 계산 — paper_engine이 사용한다."""

from __future__ import annotations

# ============================================================
# Bybit USDT-M MMR (Maintenance Margin Rate) 테이블
# ============================================================
_BYBIT_MMR: dict[int, float] = {
    1: 0.005,
    2: 0.005,
    3: 0.01,
    5: 0.01,
    10: 0.02,
    20: 0.025,
    25: 0.025,
    50: 0.03,
    64: 0.04,
}


def _get_mmr(leverage: int) -> float:
    """레버리지에 해당하는 MMR 반환.

    테이블에 없는 레버리지는 다음으로 낮은 키의 MMR을 사용한다.
    예) leverage=7 → 키 5의 MMR(0.01) 반환.
    """
    # 테이블에 정확히 있으면 바로 반환
    if leverage in _BYBIT_MMR:
        return _BYBIT_MMR[leverage]

    # 다음으로 낮은 키를 내림차순 탐색
    for key in sorted(_BYBIT_MMR.keys(), reverse=True):
        if key < leverage:
            return _BYBIT_MMR[key]

    # leverage가 테이블 최솟값보다 작으면 가장 낮은 MMR 반환
    return _BYBIT_MMR[min(_BYBIT_MMR.keys())]


# ============================================================
# 1. 청산가 계산
# ============================================================

def calc_liquidation_price(entry: float, leverage: int, direction: str) -> float:
    """Bybit USDT-M 청산가 계산.

    Args:
        entry: 진입 가격
        leverage: 레버리지 (양의 정수)
        direction: 'long' 또는 'short'

    Returns:
        청산 가격 (float)
    """
    mmr = _get_mmr(leverage)
    if direction == "long":
        return entry * (1 - 1 / leverage + mmr)
    elif direction == "short":
        return entry * (1 + 1 / leverage - mmr)
    else:
        raise ValueError(f"direction은 'long' 또는 'short'여야 합니다. 입력값: {direction!r}")
