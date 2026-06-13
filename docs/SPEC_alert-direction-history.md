# 스펙: 알림 히스토리 방향(급등/급락) 기록

작성일: 2026-06-13
상태: 구현 확정 (ouroboros seed `seed_00693e27ffd7`, ambiguity 0.065)
관련: [SPEC_paper-trading-leaderboard.md](SPEC_paper-trading-leaderboard.md), [RESEARCH_direction-signals.md](RESEARCH_direction-signals.md)

## 목표
이벤트 알림 히스토리에 **종목별 기술방향**과 **9팩터 복합 시장방향**을 함께 기록·표시해, 사후에 "언제 어떤 방향 이벤트(급등/급락/청산위험)가 떴나"를 되짚는다.

## 현행 동작 (확인 완료)
- `alert_level`(CONFIRMED_HIGH/HIGH/LIQUIDATION_RISK/WHALE)은 변동성 크기+청산위험만 담고 **상승/하락 방향 미구분**.
- 방향은 정기리포트에서만 9팩터 복합 `market_tilt`로 계산. 이벤트 알림 경로엔 없음.
- `alert_history` 기록은 `notification_dispatcher._save_alert_history()`.

## 확정 결정
- 방향 두 가지 **모두** 기록: 종목 기술방향(asset_direction) + 복합 시장방향(market_direction/confidence/z).
- **이벤트 알림만** 대상(정기리포트 제외).
- 저장 표기 `long/short/neutral`, UI 라벨만 급등/급락/중립.
- 4종 알림 전부 동일하게 방향 부착. 쿨다운/트리거 로직 불변.
- `market_tilt`는 `dispatch_event_alerts` 진입 시 **1회 계산해 사이클 공유**(옵션1).
- 실패 시 해당 컬럼 null + 알림 정상 발송.

## 종목 기술방향 산출
`technical_analyzer.analyze(df)`에서 종가 모멘텀 부호로 산출(가장 단순·견고, 지표 dict 결합 없음):
- `mom = close[-1]/close[-1-LOOKBACK] - 1` (LOOKBACK=14)
- `mom > DEADBAND(0.005)` → long, `< -DEADBAND` → short, 그 외 neutral
- `details["asset_direction"]`에 저장 → `score_aggregator`가 `AggregatedResult.asset_direction`으로 surface

## 변경 파일
| 파일 | 작업 |
|---|---|
| `app/analyzers/technical_analyzer.py` | `details["asset_direction"]` 모멘텀 부호 산출 |
| `app/analyzers/score_aggregator.py` | `AggregatedResult += asset_direction` |
| `app/notification_dispatcher.py` | `dispatch_event_alerts` 시 market_tilt 1회 계산, `_save_alert_history(…, market_tilt)` 저장 |
| `app/notifiers/message_formatter.py` | 이벤트 알림 본문에 방향 한 줄(null이면 생략) |
| `dashboard/backend/db/schema.sql` + connection `_migrate` | `alert_history += asset_direction, market_direction, market_tilt_confidence, market_tilt_z` (nullable) |
| `dashboard/backend/api/alert_routes.py` | 응답에 4필드 항상 포함(null 허용) |
| `dashboard/frontend/src/components/screens/Alerts.tsx` | 종목방향/시장방향 2컬럼(배지 + confidence/z 툴팁) |

## 검증 (AC)
1. 4종 알림 발송 시 alert_history에 asset_direction + market_direction + confidence + z 저장(계산 가능 시).
2. market_tilt 실패해도 발송·저장 무파손, market_* 만 null.
3. 조회 API 응답에 4필드 항상 포함(null 허용).
4. Alerts.tsx에 종목/시장 방향 2컬럼 급등/급락/중립 배지 + confidence/z 툴팁.
5. 텔레그램 본문 방향 한 줄(null이면 생략).
6. 기존 행/스키마 하위호환(_migrate ALTER, nullable).
7. 봇 297 + 대시보드 36 회귀 무파손 + 신규 단위테스트.

## 제약
한국어 주석 · 단순성 · 외과적 변경 · details 중복 기록 금지 · 방향 필터/정렬은 추후.
