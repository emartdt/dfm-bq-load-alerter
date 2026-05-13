import { useEffect, useMemo, useState, type ReactNode } from 'react'
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

function InfoTip({ title, children }: { title: string; children: ReactNode }) {
  return (
    <span className="info-tip" tabIndex={0} aria-label={`${title} 설명`}>
      <i className="info-icon" aria-hidden="true">ⓘ</i>
      <span className="info-tip-body" role="tooltip">
        <strong>{title}</strong>
        {children}
      </span>
    </span>
  )
}

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
        <h2 className="card-title">
          시스템 상태
          <InfoTip title="어떻게 산정되나요?">
            <ul>
              <li>
                백엔드 서버의 <code>/healthz</code> 엔드포인트를 호출해 응답이 오면{' '}
                <strong>정상</strong>, 실패하면 <strong>오류</strong>로 표시합니다.
              </li>
              <li>버전은 현재 배포된 백엔드 빌드 번호 입니다.</li>
              <li>
                서버가 죽었거나 네트워크가 끊겼을 때 가장 먼저 빨갛게 바뀌는 지표입니다.
              </li>
            </ul>
          </InfoTip>
        </h2>
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
        <h2 className="card-title">
          일별 배치 현황 (최근 {DAILY_WINDOW_DAYS}일)
          <InfoTip title="어떻게 산정되나요?">
            <ul>
              <li>
                <strong>일간(daily)</strong> 주기로 등록된 테이블만 집계 대상입니다.
                월간 테이블은 다음 카드에 따로 보여집니다.
              </li>
              <li>
                같은 테이블이 하루에 여러 번 점검되어도{' '}
                <strong>그날의 가장 마지막 결과 1건만</strong> 카운트합니다. (중복 방지)
              </li>
              <li>
                예) 06시·07시·08:20 세 번 검증된 테이블이라면, 08:20 결과만 사용합니다.
              </li>
              <li>
                <strong>성공</strong>은 모든 조건 통과,{' '}
                <strong>실패</strong>는 적재 누락·row 0·증감률 초과 중 하나라도 해당된 경우.
              </li>
              <li>날짜 기준은 한국 시간(KST) 입니다.</li>
            </ul>
          </InfoTip>
        </h2>
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
        <h2 className="card-title">
          월별 배치 현황 (최근 {MONTHLY_WINDOW_MONTHS}개월)
          <InfoTip title="어떻게 산정되나요?">
            <ul>
              <li>
                <strong>월간(monthly)</strong> 주기로 등록된 테이블만 집계 대상입니다.
              </li>
              <li>
                월간 테이블은 등록한 <strong>월 배치일</strong>에만 점검되므로,
                보통 한 달에 1~2건의 결과만 쌓입니다.
              </li>
              <li>
                같은 테이블이 한 달 안에 여러 번 점검되더라도{' '}
                <strong>그 달의 가장 마지막 결과 1건만</strong> 카운트합니다.
              </li>
              <li>
                <strong>성공</strong>은 모든 조건 통과,{' '}
                <strong>실패</strong>는 적재 누락·row 0·증감률 초과 중 하나라도 해당된 경우.
              </li>
              <li>월 기준은 한국 시간(KST) 입니다.</li>
            </ul>
          </InfoTip>
        </h2>
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
        <h2 className="card-title">
          테이블별 성공률
          <InfoTip title="어떻게 산정되나요?">
            <ul>
              <li>
                <strong>일간 테이블</strong>은 최근 {DAILY_WINDOW_DAYS}일,{' '}
                <strong>월간 테이블</strong>은 최근 {MONTHLY_WINDOW_MONTHS}개월의
                결과를 봅니다.
              </li>
              <li>
                같은 슬롯(일간=하루, 월간=한 달)에서{' '}
                <strong>가장 최근 결과 1건만</strong> 사용합니다.
              </li>
              <li>
                <strong>성공률 = 성공(ok) ÷ (성공 + 실패)</strong> · 0% ~ 100%
              </li>
              <li>
                예) 최근 30일 중 28일 성공 + 2일 실패 → 28 ÷ 30 ≒ 93.3%
              </li>
              <li>
                <strong>낮은 순으로 정렬</strong>하여 위쪽에 문제가 잦은 테이블이
                보이게 했습니다.
              </li>
              <li>
                해당 기간에 한 번도 점검되지 않은 테이블(예: 신규 등록)은 차트에
                나타나지 않습니다.
              </li>
            </ul>
          </InfoTip>
        </h2>
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
