# PLAN: KrStockChart 캔들 간격 재설계 (D/W/M)

**Seed ID:** seed_250dada0b8b8  
**작성일:** 2026-04-19

## 목표
KrStockChart 탭을 기간 범위(1w/1m/3m/6m/1y) → 캔들 간격(일/주/월)으로 재설계.  
API 파라미터: `interval=1d|1wk|1mo` (야후 표기 통일)

## 탭 구조
| 탭 | interval | 캔들 간격 | 목표 개수 |
|---|---|---|---|
| 일 | 1d | 일봉 | ~200개 |
| 주 | 1wk | 주봉 | ~200개 |
| 월 | 1mo | 월봉 | ~120개 |

## 데이터 소스 전략
- 한국 종목(.KS/.KQ): 네이버 fchart 우선 → 미지원 시 야후 fallback
- 미국 종목: 야후 단독
- 완전 실패 시: 빈 배열 반환 (에러 토스트 없음)

---

## Task 1: 네이버 fchart W/M 지원 검증 + naver_finance.py 수정

**파일:** `dashboard/backend/collectors/naver_finance.py`

1. curl로 네이버 fchart timeframe=week/month 지원 여부 검증:
   ```
   https://fchart.stock.naver.com/sise.nhn?symbol=005930&timeframe=week&count=200&requestType=0
   https://fchart.stock.naver.com/sise.nhn?symbol=005930&timeframe=month&count=120&requestType=0
   ```
2. 지원 확인 시: `timeframe` 파라미터를 interval에 맞게 매핑
   - `interval=1d` → `timeframe=day`, `count=200`
   - `interval=1wk` → `timeframe=week`, `count=200`
   - `interval=1mo` → `timeframe=month`, `count=120`
3. 미지원 시: `interval=1wk/1mo` 요청에서 `None` 반환 (yahoo fallback 트리거)
4. 함수 시그니처: `fetch_naver_ohlcv(ticker, interval="1d")`
5. 기존 `period` 파라미터 제거

---

## Task 2: yahoo_finance.py 주봉/월봉 지원 추가

**파일:** `dashboard/backend/collectors/yahoo_finance.py`

`fetch_stock_ohlcv` 함수 수정:
- 시그니처: `fetch_stock_ohlcv(ticker, interval="1d")`
- interval → Yahoo API 파라미터 매핑:
  - `1d` → `interval=1d`, `range=1y`
  - `1wk` → `interval=1wk`, `range=5y`
  - `1mo` → `interval=1mo`, `range=max`
- 기존 `_PERIOD_MAP` (period→range 매핑) 제거
- 캐시 키: `yahoo_ohlcv:{ticker}:{interval}`

---

## Task 3: stock_slots_routes.py API 파라미터 변경

**파일:** `dashboard/backend/api/stock_slots_routes.py`

`/stock-chart/{ticker}` 엔드포인트 수정:
- `period: Literal["1w","1m","3m","6m","1y"]` → `interval: Literal["1d","1wk","1mo"]`
- 기본값: `interval="1d"`
- 라우팅 로직:
  ```python
  is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
  if is_korean:
      result = await fetch_naver_ohlcv(ticker, interval)
      if result is None:  # 네이버 미지원(W/M) → 야후 fallback
          result = await fetch_stock_ohlcv(ticker, interval)
  else:
      result = await fetch_stock_ohlcv(ticker, interval)
  if result is None:
      return []  # 에러 대신 빈 배열
  return result
  ```

---

## Task 4: KrStockChart.tsx 프론트엔드 수정

**파일:** `dashboard/frontend/src/components/shared/KrStockChart.tsx`

- `type Period` → `type Interval = '1d' | '1wk' | '1mo'`
- 기본값: `'1d'`
- 탭 배열: `['1d', '1wk', '1mo']`
- 탭 레이블: `{ '1d': '일', '1wk': '주', '1mo': '월' }`
- API 호출: `/api/stock-chart/${ticker}?interval=${interval}`
- 기존 `period` 관련 변수명 모두 `interval`로 변경

---

## Acceptance Criteria

- [ ] D(일) 탭: 005930.KS, AAPL 일봉 캔들 표시
- [ ] W(주) 탭: 한국·미국 주봉 캔들 표시
- [ ] M(월) 탭: 한국·미국 월봉 캔들 표시
- [ ] 기존 1w/1m/3m/6m/1y 코드 완전 제거
- [ ] 야후 실패 시 빈 배열, "차트를 불러올 수 없습니다" 표시
