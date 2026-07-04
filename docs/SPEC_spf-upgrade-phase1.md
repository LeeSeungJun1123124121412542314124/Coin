# 스펙: SPF 업그레이드 1단계 — 유사 패턴 정규화 + 60일 horizon

작성일: 2026-07-04
상태: 스펙 확정 (ouroboros seed_67acd0bfba1c, A등급) — **구현 완료**
관련: [SPEC_spf-composite.md](SPEC_spf-composite.md), [full-review-2026-07-04.md](full-review-2026-07-04.md) L-4
구현 계획: [plans/spf-upgrade-phase1-2026-07-04.md](plans/spf-upgrade-phase1-2026-07-04.md)

## 배경 / 범위 원칙

SPF(복합 9팩터 방향 + 7/14/30일 채점)는 실측 축적 3주차. **모델 본체를 바꾸면 실측 검증이 리셋**되므로, 이번 1단계는 모델 무변경 개선 2건만 포함한다.
`direction_composite`·`generate_prediction` 로직은 건드리지 않는다.

## 업그레이드 1 — 유사 패턴 차원 정규화

### 문제
`find_similar_patterns`([spf_service.py:193-254](../dashboard/backend/services/spf_service.py))가 6차원 벡터
`[oi_change_3d, oi_change_7d, cum_fr_3d, cum_fr_7d, oi_change_14d, cum_fr_14d]`
를 정규화 없이 코사인 유사도에 넣는다. OI 변화(수% 스케일)가 누적 FR(0.000x 스케일)을 압도해 **FR 축이 유사도에 사실상 기여하지 못함** — "과거 유사 국면" 뷰의 품질 결함 (검수 L-4).

### 요구사항
- 조회된 과거 레코드(최대 500행)로 **차원별 평균·표준편차**를 구해 z-score 정규화 후 코사인 유사도 계산
- 현재 벡터도 **같은 평균·표준편차**로 변환 (히스토리 기준 통일)
- 표준편차 0인 차원은 0 처리 (해당 차원 제외 효과)
- 유사도 임계 0.85 유지. 단 정규화 후 매칭 0건 빈도 관찰용으로 매칭 수 debug 로그
- 반환 형식(date/similarity/flow/change_3d_pct/bearish_score) 무변경 — 프론트 무영향

### AC
1. 스케일 불변성: FR 차원들에 ×1000을 곱한 데이터에서도 정규화 후 유사도 **순위 동일**
2. FR 차이만 있는 두 레코드가 정규화 후 유사도에 실제로 **차등 반영** (현재는 동일하게 나옴)
3. 기존 반환 형식·호출부 무변경

## 업그레이드 2 — 60일 horizon 추가

### 근거
백테스트(2018-01~2026-06, ±1% 고정, 방향 커밋 기준)에서 **60일이 64.9%로 최고 정확도**인데 채점에 없음. 복합은 중기 신호라는 개편 결론과도 일치.

### 요구사항 (변경 파일별)

| 파일 | 작업 |
|---|---|
| `db/schema.sql` + `connection._migrate` | `predictions.result_60d` TEXT nullable 추가 (기존 result_7d/14d/30d 패턴, 하위호환) |
| `services/spf_service.py` | `EXPECTED_ACCURACY`에 `60: 64.9` 추가 (표본 주석 명시) |
| `jobs/update_predictions.py` | 다horizon 판정 루프에 `(60, "result_60d")` 추가 — 기존 `_judge_horizon` 재사용 |
| `api/spf_routes.py` | `/prediction-history` stats → `{7,14,30,60}` 각 `{expected, realized, n}` |
| `frontend SPF.tsx` | horizon 카드 3→4개. "기대 64.9% · 실측 Y% (n=N)", 중립 "기대 – · 실측 –" |

### AC
1. 마이그레이션 후 기존 행 보존, `result_60d` NULL로 시작
2. 60일 전 예측이 `_judge_horizon` 규칙(상승&>+1% hit / 하락&<−1% hit / 중립 'neutral' / 그 외 miss)으로 판정·기록
3. API 응답에 60 키 포함, 기존 7/14/30 무영향
4. 프론트 4카드 렌더 (tsc -b 빌드 통과)

## 공통 제약

한국어 주석 · 외과적 변경 · TDD(실패 테스트 먼저) · 대시보드 테스트 83개 회귀 무파손 · 새 의존성 금지(statistics 표준 라이브러리) · 마이그레이션은 기존 `_migrate` 패턴

## 이후 로드맵 (이번 범위 아님)

| 단계 | 내용 | 전제 |
|---|---|---|
| 2단계 | 신뢰도 → 확률 보정 (z구간별 경험적 적중률 매핑) | 백테스트 재실행 |
| 3단계 | 피드백 루프 — 리더보드 실측으로 복합 재가중 | 리더보드 4~6주 데이터 (7월 중하순~) |
| 4단계 | TGA 10번째 팩터 편입 판단 | 3단계와 동일 근거 데이터 |
| 보류 | 변동성 조정 임계(±1% → ATR 기반) | 기대치 테이블 전면 재산출 필요 |
