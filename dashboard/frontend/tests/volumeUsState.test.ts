import assert from 'node:assert/strict'

import { resolveUsVolumeSections } from '../src/components/screens/volumeUsState.ts'

assert.deepEqual(
  resolveUsVolumeSections({
    stock: { data: { value: 54 }, loading: false, error: null },
    putcall: { data: null, loading: false, error: new Error('putcall failed') },
  }),
  { stock: 'data', putcall: 'error' },
)

assert.deepEqual(
  resolveUsVolumeSections({
    stock: { data: null, loading: true, error: null },
    putcall: { data: { records: [] }, loading: false, error: null },
  }),
  { stock: 'loading', putcall: 'data' },
)
