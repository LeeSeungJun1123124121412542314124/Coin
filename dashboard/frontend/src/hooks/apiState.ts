// useApi가 화면에 내놓는 값 계산 — 결과·실패를 받은 주소와 지금 주소를 비교한다 (순수 함수)

export interface ApiResult<T> {
  path: string
  data: T
  at: Date
}

export interface ApiFailure {
  path: string
  message: string
}

export function deriveApiState<T>(
  path: string | null,
  result: ApiResult<T> | null,
  failure: ApiFailure | null,
  fetching: boolean,
) {
  // 지금 주소로 받은 것만 보여준다 — 주소가 바뀌면 이전 데이터·오류는 숨긴다
  const mine = result !== null && result.path === path ? result : null
  const error = failure !== null && failure.path === path ? failure.message : null
  return {
    data: mine ? mine.data : null,
    lastUpdated: mine ? mine.at : null,
    error,
    // 첫 로딩(또는 주소가 바뀐 뒤 로딩)만 loading — 같은 주소 재조회는 데이터를 유지한다
    loading: path !== null && mine === null && error === null,
    isRefreshing: mine !== null && fetching,
  }
}
