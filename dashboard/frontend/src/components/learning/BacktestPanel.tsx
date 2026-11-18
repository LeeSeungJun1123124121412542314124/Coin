import { useState } from 'react'
import { AutoBacktest } from '../shared/AutoBacktest'
import { CompositeSimulator } from '../shared/CompositeSimulator'
import { toggleStyle } from './learningShared.ts'

// 백테스트 — 기존 시뮬레이터 화면의 백테스트 토글(종합 시뮬레이션 / 지표별 분석)을 그대로 옮김
export function BacktestPanel() {
  const [backtestTab, setBacktestTab] = useState<'composite' | 'indicator'>('composite')

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['composite', 'indicator'] as const).map(tab => (
          <button key={tab} onClick={() => setBacktestTab(tab)} style={toggleStyle(backtestTab === tab)}>
            {tab === 'composite' ? '종합 시뮬레이션' : '지표별 분석'}
          </button>
        ))}
      </div>
      {backtestTab === 'composite' ? <CompositeSimulator /> : <AutoBacktest />}
    </div>
  )
}
