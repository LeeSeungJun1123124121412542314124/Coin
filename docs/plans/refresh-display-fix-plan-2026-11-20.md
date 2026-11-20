# 화면 갱신·표시 수정 계획 (2026-11-20)

- 근거: `docs/review-2026-11-20.md` 1절 4~7번. 사용자 선택 "화면 갱신·표시 먼저"
- 스펙: ouroboros seed `seed_11f9c6e2e736` (인터뷰 없이 이 세션에서 정해진 내용으로 생성). 아래 완료 기준이 그 내용이다

## 1. 지금 동작 (코드로 확인)
| 문제 | 원인 |
|---|---|
| 자동 갱신 때 화면이 뼈대로 깜빡임 | `hooks/useApi.ts`가 재조회마다 `loading`을 올리고, 화면들이 `loading \|\| !data`면 뼈대를 그린다 (Alt·Liquidity·Market·SPF·Volume·Whale·Research) |
| 주소가 바뀌어도 이전 데이터가 남음 | `useApi`가 주소가 바뀌어도 `data`를 그대로 둔다 (알림 심볼 필터에서 이전 심볼 목록이 보임) |
| 갱신 실패가 안 보임 | 화면들이 `error && !data`일 때만 오류를 그린다. 데이터가 있으면 실패 표시 없음 |
| 대시보드가 통째로 빔 | `Dashboard.tsx:345` `if (!data) return null`, `loading`·`error`를 안 쓴다 |
| "최종 갱신"이 `-` | 대시보드·리더보드·학습에 `LastUpdated`가 없다 |
| "방금 전"에서 멈춤 | `LastUpdated.tsx`가 시각이 바뀔 때 한 번만 상대 표현을 계산한다 |
| 리서치 갱신 실패 시 카드가 사라짐 | `Research.tsx:425` `error ?`가 데이터 유무와 상관없이 오류만 그린다 |

고래추적의 "최종 갱신 -"는 점검 때 응답이 늦어 생긴 착오였다(코드상 정상). 점검 문서에서 고친다.

## 2. 바꿀 것
1. `hooks/apiState.ts`(새 순수 모듈) + `tests/apiState.test.ts`: `deriveApiState(path, result, failure, fetching)` → `{ data, lastUpdated, error, loading, isRefreshing }`
   - `data`·`lastUpdated`·`error`는 지금 주소의 것만 돌려준다
   - `loading` = 주소가 있고, 그 주소의 데이터도 오류도 아직 없을 때만 참
   - `isRefreshing` = 데이터가 있는 상태에서 요청 중
2. `hooks/useApi.ts`: 결과·실패를 주소와 함께 저장하고 위 함수로 값을 낸다. 같은 주소 재조회는 이전 실패 표시를 결과가 나올 때까지 유지, 데이터 없는 조회는 시작할 때 실패를 지운다
3. `components/shared/LastUpdated.tsx`: `failed` 속성 추가, 시각을 `HH:mm`(브라우저 시간, 24시간제)으로 보내고, 시각이 없으면 빈 값을 보낸다
4. `App.tsx` + `index.css`: 머리말이 `최종 갱신 HH:mm` 또는 `갱신 실패 · 마지막 성공 HH:mm`(경고색)을 그린다
5. `LastUpdated`를 쓰는 화면 8곳: `failed={!!error}` 전달
6. `Dashboard.tsx`: 첫 로딩 뼈대, 첫 로딩 실패 시 `ErrorState`, `LastUpdated` 추가
7. `Leaderboard.tsx`, 학습(`learningShared.ts`의 `useLoader`에 받은 시각 추가 → `LearningChart.tsx`): `LastUpdated` 추가
8. `Research.tsx`: `error ?` → `error && !data ?`

## 3. 완료 기준과 검증
| # | 기준 | 검증 |
|---|---|---|
| 1 | 같은 주소 자동 갱신 중 데이터 유지, 뼈대 안 나옴 | `apiState` 단위 테스트 + 화면 확인(갱신 주기 대기 또는 탭 복귀) |
| 2 | 주소가 바뀌면 이전 데이터가 안 보임 | 단위 테스트 + 알림 심볼 필터 화면 확인 |
| 3 | 데이터 있는 상태에서 갱신 실패 → 데이터 유지 + 머리말 "갱신 실패 · 마지막 성공 HH:mm", 성공하면 사라짐 | 단위 테스트 + 화면 확인(백엔드 내렸다 올리기) |
| 4 | 머리말이 HH:mm, 대시보드·리더보드·학습도 시각 표시 | 화면 확인 |
| 5 | 대시보드 첫 로딩 뼈대, 실패 시 오류와 다시 시도 | 화면 확인(백엔드 내린 상태로 열기) |
| 6 | 리서치 갱신 실패 시 카드 유지 | 코드 + 화면 확인 |
| 7 | pytest 전체, npm test, build 통과, eslint 새 문제 없음 | 명령 실행 |

## 4. 제약
프론트만, 새 패키지 없음, 범위 밖 정리 없음, 기존 문자열 단언 테스트 유지, master 로컬 커밋, push는 승인 후
