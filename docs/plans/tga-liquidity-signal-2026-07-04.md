# TGA 유동성 신호 추가 구현 계획

**작성일:** 2026-07-04
**Seed:** seed_b4ac27eb973a (interview_20260703_171422, ambiguity 0.089)
**기능:** ① TGA 급변 이벤트 텔레그램 알림 + ② 리더보드 TGA 단독 지표

---

## 1. 배경 / 문제

- 순유동성 팩터는 `WALCL − TGA(WTREGEN) − RRP×1000`으로 TGA를 **이미 수집** 중 ([collectors.py:119-124](../../crypto-volatility-bot/app/macro/collectors.py)). 추가 데이터 비용 0.
- 문제: TGA가 합성값에 묻혀 "유동성이 왜 움직였는지" 안 보임. TGA는 세금납부·부채한도 재적립 등 이벤트성으로 단기 수천억$ 움직이는 크립토 변동성 선행 요인.
- 방침: TGA 원값 상시 노출은 노이즈 → 제외. **급변 시에만 알림**(봇의 '변화에만 알림' 철학) + **리더보드 단독 지표로 실측 검증**('검증 후 채택' 원칙).

## 2. 확정 스펙

### A. 캐시 스키마 (선행 작업)
- `fetch_sources()` 반환 dict + `_SOURCE_COLS`에 `"tga"` 추가 — TGA 원시 시계열(백만$, 주간→일봉 ffill)을 macro_cache.csv에 상시 보존.
- **마이그레이션**: `_load_sources`에서 `_SOURCE_COLS ⊄ df.columns`이면 캐시 stale 취급 → FRED 전량 재수집. (별도 스크립트/NaN 채움 없음 — 캐시는 일 1회 재수집되는 소모품)

### B. 리더보드 TGA 지표
- `build_factors()`에 `tga` 파라미터 + `"tga_13w": chg13(tga)` 출력 추가.
- `INDICATORS`에 `"TGA"` 1줄 등록. **부호 −1**(TGA↑=유동성 흡수=약세)은 SignalFn에서 처리: `lambda ctx, asset: -ctx.macro_z["tga_13w"]` (`_SIGN`은 FACTORS 유래라 FACTORS 밖 팩터는 기본 +1이므로).
- **복합방향 무변경 보장**: `compute_composite`/`latest_tilt`는 고정 `FACTORS` 9개만 순회 — `tga_13w`를 FACTORS에 넣지 않으므로 복합방향·기존 리더보드 지표 모두 불변.

### C. TGA 급변 이벤트 알림
- **판정값**: `tga_delta_4w` = TGA 4주(28일) 변화 (백만$).
- **상태머신** (bot_state 단일 키 `tga_4w_alert_state`, 3상태):

| 전이 | 조건 | 동작 |
|------|------|------|
| neutral → above_positive | Δ4W ≥ +T | 🔔 "유동성 흡수" 알림 1회 |
| neutral → above_negative | Δ4W ≤ −T | 🔔 "유동성 방출" 알림 1회 |
| above_± → neutral | \|Δ4W\| < 0.7×T (히스테리시스) | 무발화 리셋 |
| above_positive ↔ above_negative | 반대 방향 T 돌파 (0.7T 복귀 없이) | 🔔 방향 전환 알림 1회 (2T 이동 = 노이즈 아님) |
| 동일 상태 유지 | — | 무발화 |

- **훅**: 기존 `direction_health_watch` 데일리 크론(UTC 00:20)에 함수 추가 호출 (반도체 stale 알림과 동일 패턴, 별도 크론 없음).
- **기록**: `alert_history` INSERT — `symbol="TGA"`, `alert_level="MACRO_EVENT"`(신설), details JSON `{delta_4w, threshold, direction, tga_level, state}`.
- **메시지** (한국어, 방향별):
  - 증가: "💧 TGA 4주 +$X,XXX억 급증 — 재무부 유동성 흡수 국면, 순유동성 압박"
  - 감소: "💧 TGA 4주 −$X,XXX억 급감 — 재무부 유동성 방출, 완화 국면"
- **프론트**: Alerts.tsx `LEVEL_LABEL["MACRO_EVENT"]="매크로 이벤트"`, `LEVEL_COLOR="#38bdf8"`.

### D. 임계치 T 캘리브레이션 (구현 전 선행)
- 잠정 기본값 $1,500억(150_000백만$) — **캘리브레이션 결과로 대체**.
- 산식: 최근 5년 WTREGEN 주간 시계열 → **non-overlapping 4주 블록** Δ 분포(자기상관 보정) → 후보 임계치 3개(상위 10%/15%/20% 분위수)에 대해 **실제 전이 규칙(T·0.7T 히스테리시스·방향전환 재발화)을 과거 5년에 시뮬레이션** → 각 후보의 연평균 발화 횟수 보고 → **연 4~8회** 구간에 드는 값을 추천.
- 산출물: `docs/`에 캘리브레이션 리포트(임계값·분위수·발화 이력 시뮬) 저장 + 코드 상수 주석에 "산출일·방법·데이터범위" 기록.
- 절차: 스크립트 실행 → **사용자에게 값 보고 후 확정** → 코드 반영.

### E. 스코프 제외 (후속 결정)
- **FACTORS(복합방향) 편입은 이 계획 밖.** 리더보드 2~4주 실측 후 수동 판단. 판단 참고 지표 3개:
  1. 리더보드 수익률 순위 (기존 지표 대비 상대 위치)
  2. 방향 hit-rate
  3. 복합방향과의 신호 상관 (직교성 — 낮을수록 편입 가치)
- WALCL/RRP 급변 알림 — 필요해지면 같은 MACRO_EVENT 레벨 + 각자 symbol로 추가 (선반영 안 함).

## 3. 변경 파일

| 파일 | 변경 |
|------|------|
| `crypto-volatility-bot/app/macro/collectors.py` | `_SOURCE_COLS`+`"tga"`, fetch_sources에 tga 반환, `_load_sources` 누락 컬럼 감지 |
| `crypto-volatility-bot/app/macro/direction_composite.py` | `build_factors`에 tga 파라미터+`tga_13w` 출력 (FACTORS 무변경) |
| `crypto-volatility-bot/app/macro/signals.py` | `INDICATORS["TGA"]` + 부호반전 SignalFn |
| `dashboard/backend/jobs/direction_watch.py` | `check_tga_event()` 상태머신 + alert_history INSERT + 메시지 |
| `dashboard/backend/main.py` | `_direction_health_watch`에 `check_tga_event` 호출 추가 |
| `dashboard/frontend/src/components/screens/Alerts.tsx` | MACRO_EVENT 라벨/색 |
| `scripts/` 또는 일회성 | 캘리브레이션 스크립트 (FRED 수집기 재사용) |
| `docs/` | 캘리브레이션 리포트 |

## 4. 구현 순서 및 검증 기준

1. **캘리브레이션 스크립트 → 사용자 확정** — 산출: 후보 3개별 연평균 발화 횟수 + 추천 T. *(검증: 리포트가 docs/에 저장되고 연 4~8회 구간 값 존재)*
2. **캐시 + 팩터** — tga 컬럼 보존, tga_13w 산출. *(검증: 구캐시 로드 시 자동 재수집 테스트, build_factors 출력에 tga_13w 존재, FACTORS diff 0)*
3. **리더보드 지표** — INDICATORS 등록. *(검증: latest_signals 출력에 "TGA" 포함, 복합방향 z 기존과 동일)*
4. **알림 상태머신 (TDD)** — 전이 5케이스 테스트 선작성(tmp DB + 상태 주입, 기존 test_direction_watch 패턴 미러링): 최초 neutral 저장·+T 발화·재실행 무발화·0.7T 복귀 리셋·+T↔−T 방향전환 재발화. *(검증: 신규 테스트 전량 + 기존 스위트 회귀 0)*
5. **프론트 + 배선** — main.py 훅, Alerts.tsx 라벨. *(검증: tsc 통과)*

## 5. 제약 (인터뷰 확정)

- 신규 외부 의존성 없음. 임계치는 절대 달러값 상수(z-score 금지 — 메시지 해석성).
- 히스테리시스 배수 0.7 상수 (캘리브레이션 보고 시 함께 검토).
- 자기상관 무보정 분위수 사용 금지 (임계 과소 → 발화 과다 위험).
- 외과적 변경: FACTORS·기존 알림 레벨·타 팩터 로직 무손상.
