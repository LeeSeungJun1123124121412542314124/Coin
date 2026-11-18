# 학습 탭 시간봉 확장 스펙 (1h·1w·1M 추가)

- 작성일: 2026-11-18
- Seed: `seed_e552b30de236` (ouroboros, 인터뷰 없이 세션 결정으로 생성)
- 선행 스펙: `docs/plans/learning-tab-phase1-spec-2026-11-18.md` — 그 스펙의 "시간 단위: 일봉, 4시간봉"을 이 문서가 대체한다

## 1. 목표
학습 탭 차트에 1시간봉·주봉·월봉을 추가해 기존 일봉·4시간봉과 함께 5개 시간봉(1h·4h·1d·1w·1M)으로 국면과 사이클을 볼 수 있게 한다.

> 사용자: "1시간봉, 주봉, 월봉은 어디갔어 이게 있어야 싸이클을 보지"

경위: 처음 기획 초안에는 "주로 볼 시간 단위(주봉·월봉·일봉 / 일봉·4시간봉 / 기타)"가 미결 항목이었는데, 1차 인터뷰에서 따로 묻지 않고 데이터 출처 표의 "일봉·4시간봉"으로 고정했다.

## 2. 확정된 결정 (2026-11-18 사용자 선택)
| 항목 | 결정 |
|---|---|
| 시간봉 | 1h·4h·1d·1w·1M (바이낸스 현물 USDT kline 그대로) |
| 1시간봉 과거 데이터 | 상장일부터 전부 백필 |
| 주봉·월봉 과거 데이터 | 상장일부터 전부 |
| 지그재그 기본값 | 1h 3%, 4h 5%, 1d 10%, 1w 20%, 1M 30% (설정에서 각각 1~50%) |
| 1시간봉 수집 실패 | 기록만, 텔레그램 알림 없음 (다음 실행이 빠진 봉을 메움) |
| 1w·1M 수집 | 기존 일봉 수집(UTC 00:10, 재시도 04:00)에서 함께, 실패 알림은 일봉과 같음 |
| 매매 근거 | 5개 시간봉 모두에서 기록 가능. 복기 판정 가격은 일봉 종가 유지 |

## 3. 완료 기준
| # | 기준 | 검증 |
|---|---|---|
| 1 | `GET /api/learning/chart`가 5개 interval을 받아 캔들·일목·와이코프·지그재그·피보를 반환, 그 외 값은 422 | pytest |
| 2 | 새 종목 추가 시 5개 시간봉 모두 상장일부터 마감된 봉만 백필. 마감 판정은 kline closeTime 기준 | pytest |
| 3 | 백필이 끝난(done) 종목에 새 시간봉 캔들이 없으면 다음 수집에서 그 시간봉만 상장일부터 채움 | pytest |
| 4 | 1h 잡 매시 5분(UTC) 증분 수집, 실패는 기록만(알림 없음). 1w·1M은 일봉 수집에서 함께 | pytest |
| 5 | 지그재그 기본값 5개, 설정에서 1~50% 변경(범위 밖 400) | pytest |
| 6 | 일목 미래 구름 시각: 1M은 달력 기준 다음 달 1일 00:00 UTC, 나머지는 고정 간격 | pytest |
| 7 | order-context·orders가 5개 interval을 받고 그 시간봉의 일목 상태를 근거로 저장 | pytest |
| 8 | 프론트 토글 5개, 1h·4h는 시:분 표시, 설정 화면 임계값 5개 | npm test + 브라우저 확인 |
| 9 | 기존 pytest 전부·새 테스트 통과, ruff 경고 없음, npm test·build 통과 | 명령 실행 |

## 4. 제약
- 새 패키지 설치 금지, 바이낸스 현물 공개 API만(키 없음)
- 기존 `learning_candles` 테이블 그대로(스키마 변경 없음), UPSERT로 재실행해도 중복 없음
- 기존 다른 탭과 기존 1d·4h 동작은 바뀌지 않는다
- 비밀값을 로그·출력에 남기지 않는다
- push는 사용자 승인 후에만(push = Railway·OCI 자동 배포)

## 5. 코드 조사 결과 (2026-11-18, 커밋 5c3e7e8 기준)
- 테이블: `learning_candles(symbol, interval, open_time, …)`. interval 열에 CHECK 제약이 없어 스키마 변경이 필요 없다
- `collectors/binance_spot.py:15` `INTERVAL_MS`는 1d·4h만 있다. 마감 판정(`open_time + step - 1 >= now`)과 다음 페이지 커서(`open_time + step`)가 고정 간격을 가정하므로 월봉에서 틀린다 → kline의 closeTime(`row[6]`)으로 바꾼다
- `jobs/learning_collect.py:124` 증분 시작점 `last + INTERVAL_MS` → `last + 1`로 충분하다(startTime 이상인 봉부터 반환)
- `services/learning_indicators.py:14` `ichimoku(candles, interval_ms)`는 미래 시각을 고정 간격으로 만든다 → 월봉은 달력 기준이 필요하다
- `api/learning_routes.py:104·158·173` interval이 `Literal["1d","4h"]`, `:121` 지그재그 임계값을 1d·4h 이항으로 고른다
- `services/learning_settings.py:18` 지그재그 기본값 키는 `threshold_1d`·`threshold_4h`뿐이다. 저장된 설정은 DEFAULTS와 병합되므로 새 키는 기본값으로 채워진다
- 재시도(`retry_learning_daily`)는 오늘 최신 실행이 실패한 소스 중 일봉 러너에 있는 것만 다시 돌린다(`learning_collect.py:195`). 1h 잡이 같은 소스명(`binance-spot`)으로 성공을 기록하면 일봉 실패를 가리게 되므로 1h는 별도 소스명을 쓴다
- 프론트: `learningApi.ts:5` `Interval` 타입, `learningShared.ts:46` 라벨, `LearningChart.tsx:144·163·206·248-272`, `TradePanel.tsx:121`
