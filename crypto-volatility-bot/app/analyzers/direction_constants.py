"""방향 모델 상수 — 가중치·deadband·임계값(수동 튜닝 지점).

모든 방향/신뢰도 튜닝은 이 파일에서만 수행한다. 코드 로직 변경 불필요.
"""

from __future__ import annotations

# ── 신뢰도 점수 ───────────────────────────────────────────────
BASE_CONFIDENCE = 50.0      # 1차 방향 확정 시 출발점
CONFIRM_DELTA = 15.0        # 보조 카테고리(파생/온체인) confirm 가산
DIVERGENCE_DELTA = -15.0    # 보조 카테고리 divergence 감산
NUDGE_DELTA = 10.0          # MVRV/F&G 극단 컨트레리언 nudge 크기
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 100.0
CONFIDENCE_CUTOFF = 30.0    # 미만이면 방향 '중립' 강등

# ── deadband(무가산 0 구간) ──────────────────────────────────
FR_DEADBAND = 0.00005       # |FR| < 이 값이면 방향성 없음
FLOW_RATIO_LOW = 0.95       # flow_ratio 0.95~1.05는 방향성 없음
FLOW_RATIO_HIGH = 1.05

# ── MVRV 임계값 ──────────────────────────────────────────────
MVRV_OVERHEATED = 3.5       # 초과 시 숏 nudge
MVRV_UNDERVALUED = 0.8      # 미만 시 롱 nudge
MVRV_RISK_LOW = 2.5         # 2.5~3.5: 방향 미반영, '과열 위험' 부기

# ── F&G 임계값 ───────────────────────────────────────────────
FG_EXTREME_FEAR = 25        # 미만: 극단 공포 → 롱 nudge
FG_EXTREME_GREED = 75       # 초과: 극단 탐욕 → 숏 nudge
