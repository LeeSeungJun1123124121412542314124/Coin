import assert from 'node:assert/strict'

import { readAssetTab } from '../src/components/shared/assetTabUtils.ts'

function setWindow(href: string) {
  const mockWindow = {
    location: new URL(href),
    replacedUrl: '',
    history: {
      replaceState(_state: unknown, _title: string, nextUrl: string) {
        mockWindow.replacedUrl = nextUrl
        mockWindow.location = new URL(nextUrl, mockWindow.location.href)
      },
    },
  }

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: mockWindow,
  })

  return mockWindow
}

const windowMock = setWindow('https://example.test/market?asset=kr&range=30#charts')

assert.equal(readAssetTab(['coin', 'us']), 'coin')
assert.equal(windowMock.replacedUrl, '/market?asset=coin&range=30#charts')
