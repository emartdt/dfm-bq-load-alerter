import { useMemo, useState } from 'react'

export interface LineChartSeries {
  label: string
  color: string
  values: number[]
}

export interface LineChartProps {
  labels: string[]
  series: LineChartSeries[]
  height?: number
  yLabel?: string
  emptyMessage?: string
}

const PADDING = { top: 16, right: 24, bottom: 36, left: 40 }
const Y_TICKS = 4

export function LineChart({
  labels,
  series,
  height = 240,
  yLabel,
  emptyMessage = '표시할 데이터가 없습니다.',
}: LineChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)
  const [size, setSize] = useState<{ w: number }>({ w: 720 })

  const setRef = (el: HTMLDivElement | null) => {
    if (!el) return
    const w = el.clientWidth || 720
    if (w !== size.w) setSize({ w })
  }

  const { yMax, points, ticks } = useMemo(() => {
    const flat = series.flatMap((s) => s.values)
    const rawMax = flat.length > 0 ? Math.max(...flat) : 0
    const niceMax = rawMax <= 0 ? 4 : niceCeil(rawMax)
    const w = size.w
    const innerW = Math.max(0, w - PADDING.left - PADDING.right)
    const innerH = Math.max(0, height - PADDING.top - PADDING.bottom)
    const stepX =
      labels.length > 1 ? innerW / (labels.length - 1) : 0
    const xAt = (i: number) =>
      labels.length === 1
        ? PADDING.left + innerW / 2
        : PADDING.left + i * stepX
    const yAt = (v: number) =>
      PADDING.top + innerH - (niceMax === 0 ? 0 : (v / niceMax) * innerH)

    const pts = series.map((s) => ({
      ...s,
      coords: s.values.map((v, i) => [xAt(i), yAt(v)] as [number, number]),
    }))

    const tickValues: number[] = []
    for (let i = 0; i <= Y_TICKS; i += 1) {
      tickValues.push(Math.round((niceMax * i) / Y_TICKS))
    }

    return { yMax: niceMax, points: pts, ticks: tickValues }
  }, [series, labels.length, size.w, height])

  if (labels.length === 0) {
    return (
      <div className="chart-empty" style={{ height }}>
        {emptyMessage}
      </div>
    )
  }

  const w = size.w
  const innerW = Math.max(0, w - PADDING.left - PADDING.right)
  const innerH = Math.max(0, height - PADDING.top - PADDING.bottom)
  const xAt = (i: number) =>
    labels.length === 1
      ? PADDING.left + innerW / 2
      : PADDING.left + i * (innerW / (labels.length - 1))
  const yAt = (v: number) =>
    PADDING.top + innerH - (yMax === 0 ? 0 : (v / yMax) * innerH)

  // X 축 라벨은 너무 빽빽하지 않도록 균등 샘플링
  const maxLabels = Math.max(2, Math.floor(innerW / 60))
  const labelStep = Math.max(1, Math.ceil(labels.length / maxLabels))

  return (
    <div className="chart" ref={setRef}>
      <svg
        viewBox={`0 0 ${w} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={yLabel ?? '라인 차트'}
      >
        {/* 그리드 + Y 눈금 */}
        {ticks.map((tv) => {
          const y = yAt(tv)
          return (
            <g key={`tick-${tv}`}>
              <line
                x1={PADDING.left}
                x2={w - PADDING.right}
                y1={y}
                y2={y}
                className="chart-grid"
              />
              <text x={PADDING.left - 8} y={y + 4} className="chart-tick-label" textAnchor="end">
                {tv}
              </text>
            </g>
          )
        })}

        {/* X 축 라벨 */}
        {labels.map((lbl, i) => {
          if (i % labelStep !== 0 && i !== labels.length - 1) return null
          return (
            <text
              key={`xl-${i}`}
              x={xAt(i)}
              y={height - PADDING.bottom + 18}
              className="chart-tick-label"
              textAnchor="middle"
            >
              {lbl}
            </text>
          )
        })}

        {/* 라인 */}
        {points.map((s) => (
          <g key={`line-${s.label}`}>
            <polyline
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              points={s.coords.map(([x, y]) => `${x},${y}`).join(' ')}
            />
            {s.coords.map(([x, y], i) => (
              <circle
                key={`dot-${s.label}-${i}`}
                cx={x}
                cy={y}
                r={hoverIdx === i ? 4.5 : 3}
                fill={s.color}
              />
            ))}
          </g>
        ))}

        {/* 호버 영역 */}
        {labels.map((_, i) => {
          const x = xAt(i)
          const halfStep =
            labels.length > 1 ? innerW / (labels.length - 1) / 2 : innerW / 2
          return (
            <rect
              key={`hover-${i}`}
              x={x - halfStep}
              y={PADDING.top}
              width={Math.max(1, halfStep * 2)}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => setHoverIdx(null)}
            />
          )
        })}

        {/* 호버 가이드 */}
        {hoverIdx !== null && (
          <line
            x1={xAt(hoverIdx)}
            x2={xAt(hoverIdx)}
            y1={PADDING.top}
            y2={height - PADDING.bottom}
            className="chart-cursor"
          />
        )}
      </svg>

      {hoverIdx !== null && (
        <div className="chart-tooltip" role="status">
          <div className="chart-tooltip-title">{labels[hoverIdx]}</div>
          {series.map((s) => (
            <div key={s.label} className="chart-tooltip-row">
              <span className="chart-tooltip-dot" style={{ background: s.color }} />
              <span className="chart-tooltip-label">{s.label}</span>
              <span className="chart-tooltip-value">{s.values[hoverIdx] ?? 0}</span>
            </div>
          ))}
        </div>
      )}

      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.label} className="chart-legend-item">
            <span className="chart-legend-dot" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}

function niceCeil(value: number): number {
  if (value <= 0) return 4
  const exp = Math.floor(Math.log10(value))
  const base = Math.pow(10, exp)
  const fraction = value / base
  let nice: number
  if (fraction <= 1) nice = 1
  else if (fraction <= 2) nice = 2
  else if (fraction <= 5) nice = 5
  else nice = 10
  return nice * base
}
