# 스펙: SPF 예측 근본 교체 — 복합 모델 다horizon

작성일: 2026-06-13
상태: 구현 확정 (ouroboros interview_20260613_141500, ambiguity 0.07)
관련: [SPEC_paper-trading-leaderboard.md](SPEC_paper-trading-leaderboard.md), [RESEARCH_direction-signals.md](RESEARCH_direction-signals.md)

## 배경 — 진단 (코드+데이터)
SPF "3일 예측"의 적중률이 엉망인 원인:
1. FR 스케일 불일치(cum_fr raw 합 ~0.0009 vs 임계 0.02) → FR 가점 거의 0
2. 점수 0 근처 → 거의 항상 중립
3. 중립인데 confidence=85(최댓값) 버그
4. 봇 alert_level(변동성)을 bearish(방향)에 가산 → 방향 착오
5. 코사인 유사도 혼합스케일@0.85 → 비예측적
6. **3일 horizon 자체가 예측 불가** (효율적 시장)

### 데이터 근거 (로컬 백테스트 2018~2026, 3085일, ±1% 고정 임계, 방향 커밋 기준)
| horizon | 적중률 | IC |
|---|---|---|
| 3일 | 43.6% | 0.10 |
| 7일 | 49.8% | 0.14 |
| 14일 | 54.3% | 0.20 |
| 30일 | 59.2% | 0.27 |
| 60일 | 64.9% | 0.33 |

→ 복합은 **중기 신호**. 3일 교체는 무의미. horizon을 7/14/30으로 전환.

## 확정 설계
- **방향**: `app.macro.direction_composite.latest_tilt(build_factors(get_sources(...)))`. direction(long/short/neutral=상승/하락/중립), composite_z, confidence(|z| 기반, 중립 낮음 → 85 버그 제거). deadband는 latest_tilt 기존 로직 사용.
- **다horizon 7/14/30, ±1% 고정 임계(전 horizon 동일)**:
  - 기대: `EXPECTED_ACCURACY = {7:49.8, 14:54.3, 30:59.2}` (spf_service 모듈 상수, 주석 "표본 2018-01~2026-06, ±1% 고정, 방향 커밋 기준")
  - 실측: `result_7d/14d/30d` 누적 `hit/(hit+miss) + n`. 중립('neutral')·NULL 분모 제외
- **OI/FR/flow/패턴**: "파생 포지션 흐름" 정보 뷰로 유지. **방향 결정·alert_level 보정에서 완전 제외.**

## 변경 파일
| 파일 | 작업 |
|---|---|
| `dashboard/backend/services/spf_service.py` | `EXPECTED_ACCURACY` 상수, 복합 기반 `generate_prediction`(또는 신규 함수). OI/FR 점수는 뷰용으로 보존하되 방향서 분리 |
| `dashboard/backend/jobs/collect_spf.py` | 방향을 복합 tilt에서 산출(app.macro). OI/FR 레코드는 그대로 |
| `dashboard/backend/db/schema.sql` + `connection._migrate` | `predictions += result_7d/14d/30d` (nullable, 하위호환). 기존 `result` 보존 |
| `dashboard/backend/jobs/update_predictions.py` | 7/14/30일 전 예측 각 horizon 판정. 상승&>+1%→hit, 하락&<−1%→hit, 그 외 miss. 중립→'neutral' |
| `dashboard/backend/api/spf_routes.py` | `/prediction-history` stats를 `{7:{expected,realized,n},14:..,30:..}` |
| `dashboard/frontend/src/components/screens/SPF.tsx` | 복합 방향 배지 + horizon별 "기대 X% · 실측 Y% (n=N)" 3카드. 중립 "기대 – · 실측 –". OI/FR 뷰 유지 |

## 검증 (AC)
1. `direction`이 복합 tilt에서 나옴 (OI/FR 변동→direction 불변, tilt 변동→direction 변함)
2. `/prediction-history`에 7/14/30 각 `{expected,realized,n}` 분리
3. 중립 confidence가 85 아님, `|z|` 기반 낮은 값
4. 봇 alert_level 변동→direction/confidence 불변
5. OI/FR 포지션 흐름 뷰 렌더 유지
6. 복합 예외 주입 시 SPF 200·direction=null·뷰 정상
7. update_predictions 7/14/30 판정 + 중립 'neutral' 기록
8. 봇297/대시보드36 회귀 무파손 + 신규 단위테스트

## 제약
한국어 주석 · 단순성 · 외과적 변경 · TDD · 하위호환 · app.macro 재사용(sys.path) · 매크로 일1회 캐시 · Railway 신중.
