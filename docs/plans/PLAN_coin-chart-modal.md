# 대시보드 코인 카드 클릭 → TradingView 차트 모달

## Context
대시보드 "코인 가격" 섹션의 6개 카드(BTC/ETH/SOL/HYPE/INJ/ONDO) 및 BTC 히어로 카드 클릭 시 캔들 차트 + 보조지표 모달을 띄운다. 사용자 제공 참조 이미지 수준의 풍부한 차트 경험(EMA/BB/RSI/Stoch RSI/MACD/Volume) 을 빠르게 구현하기 위해 **TradingView Advanced Real-Time Chart 위젯**을 iframe 으로 임베드한다. 우리 서버의 OHLC 데이터는 사용하지 않으며, 기본 지표 계산/유지보수 부담이 사라진다.

필수 보조지표 (사용자 확정): **RSI / Stoch RSI / MACD / Volume**. EMA/BB 는 TradingView 기본 템플릿에 포함돼 자동 표시.

## 설계

**위젯 로딩**: `https://s3.tradingview.com/tv.js` 스크립트를 동적으로 `<head>` 에 1회 주입 후 `new TradingView.widget({...})` 로 컨테이너 초기화.

**심볼 매핑** (대시보드 코인 → TradingView):
| 대시보드 | TradingView |
|---|---|
| BTC | BINANCE:BTCUSDT |
| ETH | BINANCE:ETHUSDT |
| SOL | BINANCE:SOLUSDT |
| HYPE | BYBIT:HYPEUSDT |
| INJ | BINANCE:INJUSDT |
| ONDO | BINANCE:ONDOUSDT |

**위젯 옵션**:
- `theme: "dark"`, `locale: "kr"`, `timezone: "Asia/Seoul"`
- `interval: "240"` (4시간 기본), `style: "1"` (캔들)
- `studies: ["RSI@tv-basicstudies", "StochasticRSI@tv-basicstudies", "MACD@tv-basicstudies", "Volume@tv-basicstudies"]`
- `autosize: true`, `allow_symbol_change: true` (사용자가 다른 코인도 검색 가능)
- `hide_side_toolbar: false` (그리기 도구 제공)

## 변경 대상 파일

### 1. 신규 `dashboard/frontend/src/components/shared/Modal.tsx` (~50줄)
재사용 가능한 모달 오버레이.
- props: `{ open: boolean, onClose: () => void, children }`
- `position: fixed` 전체 백드롭 + 가운데 큰 카드 (max-width 1200px, height 85vh)
- ESC 키 핸들러, 백드롭 클릭 시 닫기, body scroll lock
- **body scroll lock 해제 보장**: `useEffect` cleanup에서 반드시 `document.body.style.overflow = ''` 복원. 비정상 언마운트 시 스크롤 영구 잠김 방지.
- 내부 컨테이너는 `<Card>` 미사용 — `padding: 0`인 div로 직접 구현. Card.tsx의 `padding: 16` 하드코딩이 차트 여백을 오염시킴.

### 2. 신규 `dashboard/frontend/src/components/shared/TradingViewChart.tsx` (~70줄)
TradingView 위젯 래퍼.
- props: `{ symbol: string }` (예: "BINANCE:BTCUSDT")
- `useEffect` 에서 `tv.js` 스크립트 중복 주입 방지 로직(window 전역 체크)
- **로딩 플레이스홀더**: `useState<'loading'|'ready'|'error'>('loading')`로 상태 관리. 스크립트 `onload` 콜백 후 `'ready'`로 전환. `'loading'` 동안 CSS 스피너(`border-radius: 50%`, `animation: spin`) 중앙 표시.
- **TV 로드 실패 처리**: 스크립트 `onerror` 콜백에서 `'error'`로 전환 → "차트를 불러올 수 없습니다" 텍스트 표시.
- 스크립트 로드 완료 후 `new TradingView.widget({ container_id, symbol, studies, ...옵션 })` 실행
- symbol 변경 시 위젯 재생성 (상태를 `'loading'`으로 리셋 후 재초기화)
- 언마운트 시 컨테이너 innerHTML 비움 (TradingView 정식 cleanup API 없음)

### 3. 신규 `dashboard/frontend/src/lib/tvSymbolMap.ts` (~15줄)
```ts
export const TV_SYMBOL_MAP: Record<string, string> = {
  BTC: 'BINANCE:BTCUSDT',
  ETH: 'BINANCE:ETHUSDT',
  SOL: 'BINANCE:SOLUSDT',
  HYPE: 'BYBIT:HYPEUSDT',
  INJ: 'BINANCE:INJUSDT',
  ONDO: 'BINANCE:ONDOUSDT',
}
export const toTvSymbol = (sym: string) => TV_SYMBOL_MAP[sym] ?? `BINANCE:${sym}USDT`
```

### 4. 수정 `dashboard/frontend/src/components/screens/Dashboard.tsx`
- `useState<string | null>(null)` 로 `selectedSymbol` 관리
- [Dashboard.tsx:155-165](dashboard/frontend/src/components/screens/Dashboard.tsx#L155-L165) 코인 카드: `onClick={() => setSelectedSymbol(coin.symbol)}` + `cursor: pointer` + **hover 시 테두리 밝기 강조** (`border-color: #60a5fa` 등으로 변경, `onMouseEnter/onMouseLeave` 또는 CSS className 활용)
- [Dashboard.tsx:87-126](dashboard/frontend/src/components/screens/Dashboard.tsx#L87-L126) BTC 히어로 카드: 동일 적용 (`onClick={() => setSelectedSymbol('BTC')}`). 내부 김프 미니 차트의 클릭 이벤트가 상위로 버블링되므로 카드 전체 영역에서 정상 발화.
- 모달 상단 타이틀 영역 미사용 — TradingView 위젯 내부에 심볼이 표시되어 중복 불필요.
- 렌더 최하단에:
  ```tsx
  <Modal open={!!selectedSymbol} onClose={() => setSelectedSymbol(null)}>
    {selectedSymbol && <TradingViewChart symbol={toTvSymbol(selectedSymbol)} />}
  </Modal>
  ```

## 재사용할 기존 요소
- [Card.tsx](dashboard/frontend/src/components/shared/Card.tsx) — 모달 외부 구조에는 미사용 (padding 충돌). 코인 카드 hover 강조에만 활용.
- Dashboard 기존 카드 레이아웃 — onClick/cursor 만 추가
- 타입스크립트 타입 선언: `TradingViewChart.tsx` 상단에 인라인 `declare global { interface Window { TradingView: any } }` 추가 (별도 `.d.ts` 파일 불필요)

## 보안/네트워크 고려
- TradingView 위젯은 `s3.tradingview.com` 에서 JS 로드. CSP 정책이 있다면 화이트리스트 필요. 현재 프로젝트에 CSP 미설정 확인됨.
- iframe 내부는 TradingView 도메인으로 격리되어 앱 데이터 노출 없음.
- Railway 배포 환경에서도 동일 동작 (외부 CDN 접근만 가능하면 됨).

## Acceptance Criteria (완료 기준)

다음 3가지가 모두 충족되면 구현 완료:
1. **6개 코인 카드 클릭 → 각 심볼의 TradingView 차트 모달 열림**
2. **RSI / Stoch RSI / MACD / Volume 4개 서브차트 자동 표시**
3. **ESC 키 또는 백드롭 클릭으로 모달 닫힘**

## Verification

1. 빌드:
   ```
   cd dashboard/frontend && npm run build
   ```
2. 브라우저 `Ctrl+Shift+R` 후:
   - 코인 카드 6종 순차 클릭 → 각 심볼 정상 로드 **(AC #1)**
   - 클릭 후 로딩 스피너 표시 → 3~5초 후 차트 로드
   - RSI / Stoch RSI / MACD / Volume 4개 서브차트 표시 확인 **(AC #2)**
   - ESC / 백드롭 클릭으로 모달 닫힘 **(AC #3)**
   - BTC 히어로 카드 클릭 → BTC 차트 정상 로드
   - HYPE 클릭 시 BYBIT 소스에서 로드되는지 확인
   - 네트워크 차단 시 "차트를 불러올 수 없습니다" 텍스트 표시 확인
   - 모달 내 TradingView 심볼 검색창에서 다른 코인 입력 → 차트 전환 가능
3. 콘솔에 `tv.js` 관련 에러 없음 확인

## Out of Scope
- TradingView 유료 기능(커스텀 전략, 알람 연동) — 무료 위젯 범위 내
- 우리 서버 OHLC 데이터를 위젯에 주입 (TradingView 유료 UDF API 필요)
- 다른 탭(SPF/Volume/Market)의 코인 클릭 연동 — 추후 동일 패턴으로 확장
- 모바일 최적화 (위젯 자체 반응형이지만 모달 사이징은 데스크톱 기준)
