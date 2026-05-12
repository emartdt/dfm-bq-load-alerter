import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

import {
  listEvents,
  listSnapshots,
  type EventChannel,
  type EventItem,
  type EventStatus,
  type SnapshotItem,
  type SnapshotStatus,
  type TriggerKind,
} from '../api/history'

const PAGE_SIZE = 50

const SNAPSHOT_STATUS_LABEL: Record<string, string> = {
  ok: '정상',
  fail: '실패',
  insufficient_history: '이력 부족',
}

const EVENT_STATUS_LABEL: Record<string, string> = {
  sent: '전송됨',
  failed: '실패',
  skipped: '건너뜀',
}

const CHANNEL_LABEL: Record<string, string> = {
  email: '이메일',
  teams: 'Teams',
}

const TRIGGER_LABEL: Record<string, string> = {
  check: '주기 점검',
  report: '리포트',
}

const SNAPSHOT_STATUS_HELP: Array<{ label: string; desc: string }> = [
  { label: 'ok', desc: '활성화된 모든 체크 통과 (정상 적재).' },
  {
    label: 'fail',
    desc: '실패 사유 발견 — window 내 미적재 / row_count=0 / 전일 대비 증감률 임계치 초과 등 (사유 컬럼 참고).',
  },
  {
    label: 'insufficient_history',
    desc: '전일 대비 증감률 체크가 켜져 있으나 비교할 어제 row_count 이력이 없어 판정 보류 (다른 실패가 없을 때만 부여, 이력이 쌓이면 자연 해소).',
  },
]

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

type Tab = 'snapshots' | 'events'

export function History() {
  const [tab, setTab] = useState<Tab>('snapshots')
  const [busy, setBusy] = useState<boolean>(false)
  const [error, setError] = useState<string>('')

  const [snaps, setSnaps] = useState<SnapshotItem[]>([])
  const [snapsTotal, setSnapsTotal] = useState<number>(0)
  const [snapStatus, setSnapStatus] = useState<SnapshotStatus | ''>('')

  const [events, setEvents] = useState<EventItem[]>([])
  const [eventsTotal, setEventsTotal] = useState<number>(0)
  const [eventChannel, setEventChannel] = useState<EventChannel | ''>('')
  const [eventStatus, setEventStatus] = useState<EventStatus | ''>('')
  const [trigger, setTrigger] = useState<TriggerKind | ''>('')

  const loadSnaps = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const page = await listSnapshots({
        status: snapStatus || undefined,
        limit: PAGE_SIZE,
      })
      setSnaps(page.items)
      setSnapsTotal(page.total)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }, [snapStatus])

  const loadEvents = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const page = await listEvents({
        channel: eventChannel || undefined,
        event_status: eventStatus || undefined,
        trigger_kind: trigger || undefined,
        limit: PAGE_SIZE,
      })
      setEvents(page.items)
      setEventsTotal(page.total)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }, [eventChannel, eventStatus, trigger])

  useEffect(() => {
    if (tab === 'snapshots') void loadSnaps()
    else void loadEvents()
  }, [tab, loadSnaps, loadEvents])

  return (
    <section>
      <header className="page-header">
        <h1 className="page-title">이력</h1>
        <p className="page-subtitle">점검 스냅샷과 발송된 알림 이벤트를 조회합니다.</p>
      </header>

      {error && <p className="error">{error}</p>}

      <nav className="tab-nav" aria-label="이력 탭">
        <button
          type="button"
          className={tab === 'snapshots' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('snapshots')}
        >
          점검 스냅샷
        </button>
        <button
          type="button"
          className={tab === 'events' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('events')}
        >
          알림 이벤트
        </button>
      </nav>

      {tab === 'snapshots' ? (
        <>
          <div className="actions">
            <label>
              상태 필터{' '}
              <select
                value={snapStatus}
                onChange={(e) => setSnapStatus(e.target.value as SnapshotStatus | '')}
              >
                <option value="">전체</option>
                <option value="ok">정상</option>
                <option value="fail">실패</option>
                <option value="insufficient_history">이력 부족</option>
              </select>
            </label>
            <span className="run-meta">
              {snaps.length} / {snapsTotal}건 표시
            </span>
          </div>
          <div className="table-scroll">
          <table className="grid-table">
            <thead>
              <tr>
                <th>점검 시각</th>
                <th>데이터셋.테이블</th>
                <th>
                  상태{' '}
                  <span className="info-tip" tabIndex={0}>
                    <span className="info-icon" aria-hidden="true">
                      ⓘ
                    </span>
                    <span className="info-tip-body" role="tooltip">
                      <strong>상태 의미</strong>
                      <ul>
                        {SNAPSHOT_STATUS_HELP.map((item) => (
                          <li key={item.label}>
                            <code>{item.label}</code> — {item.desc}
                          </li>
                        ))}
                      </ul>
                    </span>
                  </span>
                </th>
                <th>사유</th>
                <th>금일 rows</th>
                <th>증감률</th>
              </tr>
            </thead>
            <tbody>
              {snaps.length === 0 && !busy && (
                <tr>
                  <td colSpan={6} className="empty">
                    스냅샷이 없습니다.
                  </td>
                </tr>
              )}
              {snaps.map((s) => (
                <tr key={s.id}>
                  <td className="muted-cell">{new Date(s.checked_at).toLocaleString()}</td>
                  <td>
                    {s.dataset}.{s.table_name}
                  </td>
                  <td>
                    <span className={`status status-${s.status}`}>
                      {SNAPSHOT_STATUS_LABEL[s.status] ?? s.status}
                    </span>
                  </td>
                  <td className="muted-cell">{s.failure_reasons.join(', ') || '-'}</td>
                  <td className="numeric-cell">
                    {s.row_count !== null ? s.row_count.toLocaleString() : '-'}
                  </td>
                  <td className="numeric-cell">
                    {s.delta_percent_vs_yesterday !== null
                      ? `${s.delta_percent_vs_yesterday}%`
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </>
      ) : (
        <>
          <div className="actions">
            <label>
              채널{' '}
              <select
                value={eventChannel}
                onChange={(e) => setEventChannel(e.target.value as EventChannel | '')}
              >
                <option value="">전체</option>
                <option value="email">이메일</option>
                <option value="teams">Teams</option>
              </select>
            </label>
            <label>
              상태{' '}
              <select
                value={eventStatus}
                onChange={(e) => setEventStatus(e.target.value as EventStatus | '')}
              >
                <option value="">전체</option>
                <option value="sent">전송됨</option>
                <option value="failed">실패</option>
                <option value="skipped">건너뜀</option>
              </select>
            </label>
            <label>
              트리거{' '}
              <select
                value={trigger}
                onChange={(e) => setTrigger(e.target.value as TriggerKind | '')}
              >
                <option value="">전체</option>
                <option value="check">주기 점검</option>
                <option value="report">리포트</option>
              </select>
            </label>
            <span className="run-meta">
              {events.length} / {eventsTotal}건 표시
            </span>
          </div>
          <div className="table-scroll">
          <table className="grid-table">
            <thead>
              <tr>
                <th>발송 시각</th>
                <th>트리거</th>
                <th>채널</th>
                <th>상태</th>
                <th>요약</th>
                <th>오류</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 && !busy && (
                <tr>
                  <td colSpan={6} className="empty">
                    이벤트가 없습니다.
                  </td>
                </tr>
              )}
              {events.map((e) => (
                <tr key={e.id}>
                  <td className="muted-cell">{new Date(e.sent_at).toLocaleString()}</td>
                  <td>{TRIGGER_LABEL[e.trigger_kind] ?? e.trigger_kind}</td>
                  <td>{CHANNEL_LABEL[e.channel] ?? e.channel}</td>
                  <td>
                    <span className={`status status-${e.status}`}>
                      {EVENT_STATUS_LABEL[e.status] ?? e.status}
                    </span>
                  </td>
                  <td className="muted-cell" title={e.payload_summary ?? ''}>
                    {e.payload_summary && e.payload_summary.length > 64
                      ? `${e.payload_summary.slice(0, 64)}…`
                      : e.payload_summary ?? ''}
                  </td>
                  <td className="muted-cell" title={e.error ?? ''}>
                    {e.error && e.error.length > 64
                      ? `${e.error.slice(0, 64)}…`
                      : e.error ?? ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </>
      )}
    </section>
  )
}
