# 구현 계획: SPF 업그레이드 1단계 — 유사 패턴 정규화 + 60일 horizon

작성일: 2026-07-04
스펙: [SPEC_spf-upgrade-phase1.md](../SPEC_spf-upgrade-phase1.md) (ouroboros seed_67acd0bfba1c)
상태: **구현 완료 — 검증 통과**

## 진행 원칙

- TDD: 각 단계 RED(실패 테스트) → GREEN(최소 구현) → 검증 순서 고정
- 커밋 2개: 정규화 1커밋, 60d horizon 1커밋 (목적별 분리)
- 복합 방향 모델(direction_composite·generate_prediction) 무접촉

## Part A — 유사 패턴 차원 정규화

### A-1. RED: 실패 테스트 작성
`dashboard/tests/test_spf_similar_patterns.py` (신규):
1. `test_scale_invariance` — 동일 데이터에서 FR 차원만 ×1000 스케일한 DB로도 유사도 **순위 동일**해야 함 (현재는 순위 변동 → 실패)
2. `test_fr_dimension_contributes` — OI 동일·FR만 크게 다른 두 과거 레코드의 유사도가 **차등**이어야 함 (현재는 사실상 동일 → 실패)
3. `test_return_shape_unchanged` — 반환 키(date/similarity/flow/change_3d_pct/bearish_score) 검증
- DB 픽스처: 기존 `test_paper_engine.py`의 `paper_db` 패턴(connection._DB_PATH monkeypatch) 재사용, `spf_records`에 합성 레코드 INSERT
- **검증**: `pytest dashboard/tests/test_spf_similar_patterns.py` → 1·2번 실패(순위/차등 불일치), 3번 통과 확인

### A-2. GREEN: spf_service.py 구현
- `find_similar_patterns` 내부에서 rows 조회 후:
  1. 차원별 mean/std 계산 (`statistics.mean`/`pstdev`, 표준편차 0이면 해당 차원 0 고정)
  2. 과거 벡터·현재 벡터 모두 `(x - mean) / std`로 변환
  3. 변환된 벡터로 기존 `_cosine_similarity` 호출
- 매칭 수 debug 로그 1줄 (`logger.debug("유사 패턴 매칭 %d건", len(scored))`)
- **검증**: A-1 테스트 전체 통과 + `pytest dashboard/tests -q` 회귀(83개) 무파손

### A-3. 커밋
`4447e73 fix: 유사 패턴 유사도 차원 정규화`

## Part B — 60일 horizon 추가

### B-1. RED: 실패 테스트 작성
`dashboard/tests/test_spf_composite.py`에 추가:
1. `test_judge_60d_hit` — 60일 전 예측(상승, +5%)이 `result_60d='hit'`로 기록 (현재 컬럼·판정 없음 → 실패)
2. `test_migration_adds_result_60d` — 임시 DB 초기화 후 `predictions` 테이블에 `result_60d` 컬럼 존재
- **검증**: 두 테스트 실패 확인 (no such column)

### B-2. GREEN: 백엔드 구현
1. `db/schema.sql`: `predictions`에 `result_60d TEXT` 추가
2. `db/connection.py` `_migrate`: `ALTER TABLE predictions ADD COLUMN result_60d TEXT` (기존 result_7d 마이그레이션과 동일 패턴, 이미 있으면 무해)
3. `services/spf_service.py`: `EXPECTED_ACCURACY = {7: 49.8, 14: 54.3, 30: 59.2, 60: 64.9}` (주석: 표본 2018-01~2026-06, ±1% 고정, 방향 커밋 기준)
4. `jobs/update_predictions.py`: 판정 루프에 `(60, "result_60d")` 추가
5. `api/spf_routes.py`: `/prediction-history` stats 루프에 60 포함
- **검증**: B-1 테스트 통과 + `pytest dashboard/tests -q` 전체 통과

### B-3. 프론트 구현
- `SPF.tsx`: horizon 카드 배열에 60 추가 (3→4카드). 타입/렌더는 기존 7/14/30 카드 패턴 복제
- **검증**: `cd dashboard/frontend && npm run build` (tsc -b 포함) 통과 — `--noEmit`만으로 검증 금지 (지난 회귀 교훈)

### B-4. 커밋
`8311116 feat: SPF 60일 horizon 채점 추가`

## 최종 검증 체크리스트

- [x] `pytest dashboard/tests -q` 전체 통과 (기존 83 + 신규)
- [x] `ruff check crypto-volatility-bot/app dashboard/backend --select E,F,W --ignore E501` 0건 (CI 명령 그대로)
- [x] `npm run build` 통과
- [x] 마이그레이션 하위호환: 기존 DB 파일로 서버 기동 시 오류 없음 (임시 DB 픽스처가 대변)
- [x] 60d 실측 n은 배포 후 60일 뒤부터 쌓이기 시작함을 사용자에게 고지

## 리스크 / 유의점

- **정규화 후 0.85 임계**: z-score 공간에서 코사인 0.85는 원시 공간보다 엄격할 수 있음 → 매칭 0건이 잦으면 임계 하향(예: 0.7)을 별도 조정. 이번 구현에서는 임계 변경하지 않음(관찰 로그만)
- **spf_records 이력 소실 케이스**: 과거 레코드 8행 미만이면 std 추정이 불안정 — 기존 동작(빈 결과)과 동일하게 조기 반환 허용
- 60d 판정은 `date.today() - 60일`의 예측을 채점하므로, 배포 즉시 과거 예측(4월 말 이전 spf_records 있는 것)부터 소급 판정될 수 있음 — 정상 동작
