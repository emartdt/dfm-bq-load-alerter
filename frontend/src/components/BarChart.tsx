export interface BarChartItem {
  key: string | number
  label: string
  /** 0.0 ~ 1.0 — bar fill ratio. */
  value: number
  /** 본 값 옆에 작게 표시할 보조 정보 (예: "12/16"). */
  secondary?: string
  /** 라벨 옆에 표기할 칩 (예: 'daily'). */
  tag?: string
}

export interface BarChartProps {
  items: BarChartItem[]
  emptyMessage?: string
  /** 막대 색 결정 함수. 미지정 시 비율에 따른 신호등 색. */
  colorOf?: (value: number) => string
}

export function BarChart({
  items,
  emptyMessage = '표시할 데이터가 없습니다.',
  colorOf = defaultColor,
}: BarChartProps) {
  if (items.length === 0) {
    return <div className="chart-empty" style={{ height: 160 }}>{emptyMessage}</div>
  }
  return (
    <div className="bar-chart">
      {items.map((it) => {
        const pct = Math.max(0, Math.min(1, it.value)) * 100
        return (
          <div className="bar-row" key={it.key}>
            <div className="bar-label" title={it.label}>
              <span className="bar-label-text">{it.label}</span>
              {it.tag && <span className="bar-tag">{it.tag}</span>}
            </div>
            <div className="bar-track" aria-hidden="true">
              <div
                className="bar-fill"
                style={{ width: `${pct}%`, background: colorOf(it.value) }}
              />
            </div>
            <div className="bar-value">
              <span className="bar-value-pct">{pct.toFixed(1)}%</span>
              {it.secondary && <span className="bar-value-sub">{it.secondary}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function defaultColor(v: number): string {
  if (v >= 0.95) return '#248a3d' // status-ok
  if (v >= 0.8) return '#b25000' // status-warn
  return '#c92016' // status-fail
}
