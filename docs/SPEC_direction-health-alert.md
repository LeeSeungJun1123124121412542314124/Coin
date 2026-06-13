# 스펙: 복합 방향 전환 + 데이터 헬스 알림

작성일: 2026-06-14
상태: 구현
배경: 시스템이 잘 관측하지만 수동적 — 가장 검증된 신호(복합 방향)는 12h 리포트에만, 데이터 헬스 모니터는 화면에만. 결정적 순간에 푸시가 없음. → 능동 알림 추가.

## 알림 2종 (매일 1회, UTC 00:20 — 매크로 수집 갱신 후)
1. **복합 방향 전환**: 복합이 강세↔약세↔중립으로 **바뀌는 순간** 텔레그램 푸시. (전환 시점이 가장 actionable)
2. **데이터 헬스 악화**: macro_health 상태가 `stale`/`no_data`로 **전이될 때** 1회 푸시. (복합이 조용히 죽는 것 방지)

## 설계
- `macro_health()`가 status + 복합 direction을 함께 주므로 **한 번 호출로 둘 다** 처리.
- 직전 상태를 `bot_state(key,value)` 테이블에 저장 → "바뀐 순간만" 알림(중복 방지).
- 헬스가 비정상일 땐 방향 전환 알림 안 함(복합 신뢰 불가).
- 발송은 기존 dispatcher의 TelegramNotifier 재사용.

## 구성
| 파일 | 작업 |
|---|---|
| `dashboard/backend/jobs/direction_watch.py` | 신규 — `check_direction_and_health(health=None) -> list[str]` |
| `dashboard/backend/db/schema.sql` | `bot_state` 테이블 추가 (IF NOT EXISTS, 마이그레이션 불필요) |
| `dashboard/backend/main.py` | `_direction_health_watch` 잡 등록(00:20 UTC), dispatcher notifier로 발송 |

## 상태 전이 규칙
- 헬스: `stale/no_data` 진입 시 1회. 정상→비정상에서만(연속 비정상 반복 안 함).
- 방향: 직전 방향 존재 + 현재와 다를 때. 첫 실행(직전 없음)은 알림 없이 상태만 저장.

## 검증 (AC)
1. 첫 실행: 알림 없음, 상태만 저장
2. 방향 전환(long→short): "방향 전환" 메시지 1건
3. 동일 방향: 알림 없음
4. 헬스 악화(ok→stale): "데이터 상태 경고" 1건
5. 연속 비정상: 반복 알림 없음
6. 헬스 비정상이면 방향 전환 알림 안 함
7. 대시보드 회귀 무파손 + 단위테스트
