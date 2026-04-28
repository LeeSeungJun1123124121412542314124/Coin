# 봇 지표 확장 + 대시보드 업그레이드 실행 계획

## Context

기존 플랜(`glowing-gliding-pnueli.md`)의 10개 태스크를 Subagent-Driven Development로 실행한다.
봇 분석 정밀도 향상(MVRV, OBV, MFI, VWAP) + 대시보드 UX 강화(알림 히스토리, 김프 차트, 스테이블코인, 해시레이트, OI 변화율) + 알림 포맷 업그레이드.

## 실행 전략

**Subagent-Driven Development** 적용:
- 태스크별 fresh subagent 디스패치
- 2단계 리뷰: spec compliance → code quality
- 의존관계에 따른 순차 실행

## 실행 순서 (의존관계 반영)

| 순서 | Task | 내용 | 모델 |
|------|------|------|------|
| 1 | Task 1 | MVRV Ratio 추가 | sonnet (2-3파일 수정) |
| 2 | Task 3 | OBV 지표 추가 | sonnet (새 파일 + 2파일 수정) |
| 3 | Task 4 | MFI 지표 추가 | sonnet (Task 3과 동일 패턴) |
| 4 | Task 7 | VWAP 추가 | sonnet (동일 패턴) |
| 5 | Task 5 | 김치 프리미엄 히스토리 | sonnet (DB + 수집기 + API) |
| 6 | Task 6 | 스테이블코인 시가총액 | sonnet (coingecko 수정) |
| 7 | Task 9 | BTC 해시레이트 | sonnet (새 collector) |
| 8 | Task 8 | OI 변화율 | sonnet (기존 데이터 활용) |
| 9 | Task 2 | 알림 히스토리 DB + 쿨다운 | sonnet (DB 스키마 + 리팩터링) |
| 10 | Task 10 | 봇 알림 포맷 업그레이드 | sonnet (모든 지표 완성 후) |

## 각 태스크별 상세 (원본 플랜 참조)

원본 플랜: `C:\Users\USER-L\.claude\plans\glowing-gliding-pnueli.md`
각 태스크의 상세 스펙(파일, 로직, DB 스키마)은 원본 플랜에 정의됨.

## 워크플로우 (태스크당)

1. Implementer subagent 디스패치 (태스크 전문 + 컨텍스트 제공)
2. Spec compliance review subagent
3. Code quality review subagent (superpowers:code-reviewer)
4. TodoWrite 완료 마킹

## 프론트엔드 제외

프론트엔드 작업(게이지 카드, 차트 등)은 백엔드 API가 모두 완성된 후 별도 세션에서 진행.
이번 세션: **백엔드 + 봇 로직만** 구현.

## 검증

- `python -m pytest crypto-volatility-bot/tests/ -q` — 봇 테스트 통과
- `python -m pytest dashboard/tests/ -q` — 대시보드 테스트 통과
- 각 태스크별 self-review + 2단계 리뷰 통과
