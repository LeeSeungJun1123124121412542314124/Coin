# 검수 후속 진행 현황 — 2026-07-04

원본: [full-review-2026-07-04.md](full-review-2026-07-04.md)
갱신: 2026-07-04 (후속 커밋·푸시 완료 시점)

상태 범례: ✅ 완료(커밋됨) · ⏸ 보류(코드 미변경) · ⬜ 미착수 · ⚠️ 사용자 확인 대기

---

## 1. 완료 (✅) — 이번 세션 커밋

| 항목 | 내용 | 커밋 |
|---|---|---|
| A-2 | SPA catch-all 경로 탐색 차단 | 851129a |
| B-1 | 봇 로거 app 네임스페이스 — 모듈 로그 유실 해소 | b354446 |
| B-2 | 고래 알림 소생 (유동량 급증 감지) | 387a200 |
| B-3 | 알림 전송 성공 후 쿨다운 + 에러 HTML escape | e18f5af |
| B-4 | SPF 미판정 경고 로깅 | 30b36ed |
| C-1 | 리밸런스 멱등화 (같은 날 이중 반영 방지) | 30b36ed |
| C-2 | `_clamp(NaN)` → 50 (만점 둔갑 방지) | e18f5af |
| D-1 | 프론트 ErrorBoundary (렌더 크래시 격리) | 6c66a7c |
| D-2 | 폴링 실패 시 화면 유지 (`error && !data`) | 6c66a7c |
| D-3 | PIN 로그인 fetch BASE 통일 | 6c66a7c |

## 1.5. 이번 후속 진행 (커밋·푸시됨)

| 항목 | 상태 | 내용 | 검증 | 커밋 |
|---|---|---|---|---|
| B-3c | ✅ 구현 | direction/semiconductor/TGA 알림 상태를 발송 성공 후 일괄 커밋하도록 변경. 배치 중 하나라도 발송 실패 시 상태·alert_history 미커밋 | RED 확인 후 `dashboard/tests/test_direction_watch.py` 등 관련 테스트 통과 | 6c9718d |
| C-5 | ✅ 구현 | crypto 예측 채점을 `expiry_time` 이하의 가장 가까운 1h 봉 기준으로 변경. SL/TP/청산 판정도 만료 시점 기준. 신규 입력은 timezone-aware ISO로 강제 | `dashboard/tests/test_settle_predictions.py` 통과 | 5fc66e0 |
| C-3 | ⏸ 부분 구현 | ATR 정규화를 가격 대비 %로 전환하고 운영 config 회귀 테스트 추가 | 테스트 통과. 단, 새 임계값 min/max의 백테스트 재도출 근거는 아직 없음 | 04d61a5 |
| E | ✅ 구현 | Docker/CI가 `requirements-lock.txt` constraints 사용, Docker gcc/g++ 제거, frontend `npm ci`, CI Python 3.12 정렬, package-lock 동기화 | Python 3.12 Linux wheel-only 해석 통과, `npm ci --dry-run` 통과 | c51d06d |

## 2. 보안 — 사용자 확인 대기 (⚠️, 이번 범위서 제외)

| 항목 | 등급 | 필요 조치 |
|---|---|---|
| A-1 | 높음 | 루트 DB 덤프 4종(`crypto_dump.sql`·`crypto_inserts.sql`·`ohlcv_inserts.sql`·`crypto_b64.txt`) 삭제 여부 확인 + .gitignore 추가 |
| A-3 | 높음 | Railway에 `PIN_CODE`/`APP_SECRET`/`ADMIN_KEY` 실제 설정 확인 + 기본값 폴백 제거 |

## 3. 보류 — 별도 신중 작업 필요 (⏸)

| 항목 | 등급 | 보류 사유 |
|---|---|---|
| C-3 | 중간 | ETH ATR 정규화는 % 기반으로 구현했으나, 새 임계값 min/max의 **백테스트 재도출** 근거가 아직 없음 |

## 4. 정정 (원본 보고서 대비)

- **C-4 (async 이벤트루프 블로킹) → 사실상 해당 없음(낮음)**: 확인 결과 `run_paper_rebalance`는 sync 함수라 APScheduler가 스레드풀에서 실행 → 이벤트루프 블로킹 아님. `settle_expired_predictions`만 미미하게 해당. 원본의 "중간"은 과대평가.

## 5. 남은 낮음 항목 (⬜, 점진 처리)

### E. 저장소·배포 위생

| 항목 | 등급 | 내용 |
|---|---|---|
| 루트 README 없음 / 4월 문서 아카이브 | 낮음 | 모노레포 구조 설명 부재, 낡은 기획 문서 잔존 |

### C-6 / D-4 (정리 성격, 크래시 아님)

- DerivativesAnalyzer SHORT_CROWDED 도달 불가 분기 (dead code, 의도 확인 후 삭제)
- rsi_extreme 쿨다운이 yaml 주석 의도와 반대 동작으로 보임 (확인 필요)
- RSI 워밍업 NaN을 100으로 fillna
- OI 데이터 2~3개일 때 3일 변화율 왜곡
- sim_engine `_fetch_funding_rate` 항상 0 (미구현 플레이스홀더)
- 분석기 4종 심볼·사이클마다 재생성 (YAML 재파싱)
- Simulator 숨겨진 뷰용 API 6회 낭비 호출
- PIN 빠른 연타 시 자릿수 유실 / TradingView 로드 실패 무한 스피너
- `frontend/.env`의 `VITE_PIN_CODE=0000` 잔재 삭제

---

## 요약

- **중간 이상 남은 것**: C-3 백테스트 재도출 (+ 보안 A-1·A-3)
- **낮음만 남은 것**: E 나머지 · C-6 · D-4
- 크래시·데이터 유실급 중간 항목은 이번 세션에서 모두 처리됨. 남은 중간은 임계값 재검증과 사용자 확인이 필요한 것들.
