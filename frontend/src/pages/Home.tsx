import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { BarChart, type BarChartItem } from '../components/BarChart'
import { LineChart } from '../components/LineChart'
import {
  getDailyStats,
  getMonthlyStats,
  getTableSuccessRate,
  type DailyStatPoint,
  type MonthlyStatPoint,
  type TableSuccessRateRow,
} from '../api/stats'

type HealthStatus = 'unknown' | 'ok' | 'error'

interface VersionResponse {
  version: string
}

const HEALTH_LABEL: Record<HealthStatus, string> = {
  unknown: '확인 중',
  ok: '정상',
  error: '오류',
}

const COLOR_OK = '#248a3d'
const COLOR_FAIL = '#c92016'

const DAILY_WINDOW_DAYS = 30
const MONTHLY_WINDOW_MONTHS = 12

export function Home() {
  const [health, setHealth] = useState<HealthStatus>('unknown')
  const [version, setVersion] = useState<string>('')
  const [daily, setDaily] = useState<DailyStatPoint[] | null>(null)
  const [monthly, setMonthly] = useState<MonthlyStatPoint[] | null>(null)
  const [rates, setRates] = useState<TableSuccessRateRow[] | null>(null)
  const [statsError, setStatsError] = useState<string>('')

  useEffect(() => {
    fetch('/healthz')
      .then((res) => (res.ok ? setHealth('ok') : setHealth('error')))
      .catch(() => setHealth('error'))

    fetch('/api/version')
      .then((res) => res.json() as Promise<VersionResponse>)
      .then((data) => setVersion(data.version))
      .catch(() => setVersion('?'))
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [d, m, r] = await Promise.all([
          getDailyStats(DAILY_WINDOW_DAYS),
          getMonthlyStats(MONTHLY_WINDOW_MONTHS),
          getTableSuccessRate({
            days: DAILY_WINDOW_DAYS,
            months: MONTHLY_WINDOW_MONTHS,
          }),
        ])
        if (cancelled) return
        setDaily(d.points)
        setMonthly(m.points)
        setRates(r.rows)
      } catch (err) {
        if (cancelled) return
        setStatsError(err instanceof Error ? err.message : String(err))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const dailyChart = useMemo(
    () => buildDailySeries(daily ?? [], DAILY_WINDOW_DAYS),
    [daily],
  )
  const monthlyChart = useMemo(
    () => buildMonthlySeries(monthly ?? [], MONTHLY_WINDOW_MONTHS),
    [monthly],
  )

  const rateItems = useMemo<BarChartItem[]>(() => {
    if (!rates) return []
    return [...rates]
      .sort((a, b) => a.success_rate - b.success_rate || a.table_name.localeCompare(b.table_name))
      .map((r) => ({
        key: r.table_id,
        label: `${r.dataset}.${r.table_name}`,
        value: r.success_rate,
        secondary: `${r.ok_count}/${r.total}`,
        tag: r.frequency,
      }))
  }, [rates])

  return (
    <section>
      <header className="page-header">
        <h1 className="page-title">대시보드</h1>
        <p className="page-subtitle">BigQuery 적재 모니터링과 알림 정책을 한 곳에서.</p>
      </header>

      <div className="card">
        <h2 className="card-title">시스템 상태</h2>
        <p className="meta">
          백엔드 <span className={`badge badge-${health}`}>{HEALTH_LABEL[health]}</span>
          {version && <span> · v{version}</span>}
        </p>
        <p style={{ marginTop: 16 }}>
          <Link to="/tables" className="btn btn-primary btn-small">
            테이블 관리로 이동
          </Link>
        </p>
      </div>

      {statsError && <p className="error">통계 조회 실패: {statsError}</p>}

      <div className="card">
        <h2 className="card-title">일별 배치 현황 (최근 {DAILY_WINDOW_DAYS}일)</h2>
        <p className="card-subtitle">
          daily 적재 대상 테이블의 KST 일자별 성공/실패 카운트.
        </p>
        {daily === null && !statsError ? (
          <div className="chart-empty" style={{ height: 240 }}>로딩 중…</div>
        ) : (
          <LineChart
            labels={dailyChart.labels}
            series={dailyChart.series}
            height={260}
            yLabel="일별 배치 성공/실패"
          />
        )}
      </div>

      <div className="card">
        <h2 className="card-title">월별 배치 현황 (최근 {MONTHLY_WINDOW_MONTHS}개월)</h2>
        <p className="card-subtitle">
          monthly 적재 대상 테이블의 KST 월별 성공/실패 카운트.
        </p>
        {monthly === null && !statsError ? (
          <div className="chart-empty" style={{ height: 240 }}>로딩 중…</div>
        ) : (
          <LineChart
            labels={monthlyChart.labels}
            series={monthlyChart.series}
            height={260}
            yLabel="월별 배치 성공/실패"
          />
        )}
      </div>

      <div className="card">
        <h2 className="card-title">테이블별 성공률</h2>
        <p className="card-subtitle">
          daily 최근 {DAILY_WINDOW_DAYS}일 · monthly 최근 {MONTHLY_WINDOW_MONTHS}개월
          ok/(ok+fail) 비율. 낮은 순서로 정렬.
        </p>
        {rates === null && !statsError ? (
          <div className="chart-empty" style={{ height: 160 }}>로딩 중…</div>
        ) : (
          <BarChart items={rateItems} emptyMessage="집계 가능한 스냅샷이 없습니다." />
        )}
      </div>
    </section>
  )
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function buildDailySeries(points: DailyStatPoint[], windowDays: number) {
  // KST 기준 오늘부터 windowDays 만큼 거꾸로 빈 칸을 채운다.
  const kstNow = new Date(
    new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }),
  )
  const map = new Map(points.map((p) => [p.bucket, p]))
  const labels: string[] = []
  const ok: number[] = []
  const fail: number[] = []
  for (let i = windowDays - 1; i >= 0; i -= 1) {
    const d = new Date(kstNow.getFullYear(), kstNow.getMonth(), kstNow.getDate() - i)
    const iso = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
    const hit = map.get(iso)
    labels.push(`${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}`)
    ok.push(hit?.ok_count ?? 0)
    fail.push(hit?.fail_count ?? 0)
  }
  return {
    labels,
    series: [
      { label: '성공', color: COLOR_OK, values: ok },
      { label: '실패', color: COLOR_FAIL, values: fail },
    ],
  }
}

function buildMonthlySeries(points: MonthlyStatPoint[], windowMonths: number) {
  const kstNow = new Date(
    new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }),
  )
  const map = new Map(points.map((p) => [p.bucket, p]))
  const labels: string[] = []
  const ok: number[] = []
  const fail: number[] = []
  for (let i = windowMonths - 1; i >= 0; i -= 1) {
    const d = new Date(kstNow.getFullYear(), kstNow.getMonth() - i, 1)
    const key = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`
    const hit = map.get(key)
    labels.push(`${d.getFullYear().toString().slice(2)}/${pad2(d.getMonth() + 1)}`)
    ok.push(hit?.ok_count ?? 0)
    fail.push(hit?.fail_count ?? 0)
  }
  return {
    labels,
    series: [
      { label: '성공', color: COLOR_OK, values: ok },
      { label: '실패', color: COLOR_FAIL, values: fail },
    ],
  }
}
