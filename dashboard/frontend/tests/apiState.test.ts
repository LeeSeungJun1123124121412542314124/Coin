import assert from 'node:assert/strict'
import { deriveApiState } from '../src/hooks/apiState.ts'

const at = new Date('2026-11-20T00:00:00Z')

// 첫 로딩: 데이터도 오류도 없으면 loading
assert.deepEqual(deriveApiState('/a', null, null, true), {
  data: null, lastUpdated: null, error: null, loading: true, isRefreshing: false,
})

// 같은 주소 재조회 중: 데이터 유지, loading은 거짓, isRefreshing만 참
assert.deepEqual(deriveApiState('/a', { path: '/a', data: 1, at }, null, true), {
  data: 1, lastUpdated: at, error: null, loading: false, isRefreshing: true,
})

// 주소가 바뀌면 이전 주소의 데이터·시각·오류는 보이지 않고 loading
assert.deepEqual(
  deriveApiState('/b', { path: '/a', data: 1, at }, { path: '/a', message: 'HTTP 500' }, false),
  { data: null, lastUpdated: null, error: null, loading: true, isRefreshing: false },
)

// 데이터가 있는 상태에서 갱신 실패: 데이터와 마지막 성공 시각 유지 + 오류
assert.deepEqual(
  deriveApiState('/a', { path: '/a', data: 1, at }, { path: '/a', message: 'HTTP 500' }, false),
  { data: 1, lastUpdated: at, error: 'HTTP 500', loading: false, isRefreshing: false },
)

// 첫 로딩 실패: 오류만, loading은 거짓
assert.deepEqual(deriveApiState('/a', null, { path: '/a', message: 'HTTP 500' }, false), {
  data: null, lastUpdated: null, error: 'HTTP 500', loading: false, isRefreshing: false,
})

// 주소 없음(조회 안 함): loading 아님
assert.deepEqual(deriveApiState(null, { path: '/a', data: 1, at }, null, false), {
  data: null, lastUpdated: null, error: null, loading: false, isRefreshing: false,
})

// 지금 주소의 데이터 + 다른 주소의 실패: 오류는 숨기고 데이터 유지
assert.deepEqual(
  deriveApiState('/a', { path: '/a', data: 1, at }, { path: '/b', message: 'HTTP 500' }, false),
  { data: 1, lastUpdated: at, error: null, loading: false, isRefreshing: false },
)

// 이전 주소의 데이터 + 지금 주소의 실패: 오류만 보인다
assert.deepEqual(
  deriveApiState('/b', { path: '/a', data: 1, at }, { path: '/b', message: 'HTTP 500' }, false),
  { data: null, lastUpdated: null, error: 'HTTP 500', loading: false, isRefreshing: false },
)

console.log('apiState ok')
