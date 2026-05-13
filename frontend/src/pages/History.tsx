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

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const

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
]

const EVENT_STATUS_HELP: Array<{ label: string; desc: string }> = [
  { label: 'sent', desc: '대상 채널로 정상 발송 완료.' },
  {
    label: 'failed',
    desc: '발송을 시도했으나 SMTP/HTTP 호출이 예외로 실패 (네트워크·인증·타임아웃 등). 오류 컬럼에 원인 기록 — 채널 장애 신호.',
  },
  {
    label: 'skipped',
    desc: '설정 부재로 발송을 시도하지 않음 (SMTP 미설정 / 활성 수신자 없음 / webhook_url 비어있음 등). 채널 장애가 아닌 설정 점검 신호.',
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
  const [snapPage, setSnapPage] = useState<number>(1)
  const [snapPageSize, setSnapPageSize] = useState<number>(50)

  const [events, setEvents] = useState<EventItem[]>([])
  const [eventsTotal, setEventsTotal] = useState<number>(0)
  const [eventChannel, setEventChannel] = useState<EventChannel | ''>('')
  const [eventStatus, setEventStatus] = useState<EventStatus | ''>('')
  const [trigger, setTrigger] = useState<TriggerKind | ''>('')
  const [eventPage, setEventPage] = useState<number>(1)
  const [eventPageSize, setEventPageSize] = useState<number>(50)

  const loadSnaps = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const page = await listSnapshots({
        status: snapStatus || undefined,
        limit: snapPageSize,
        offset: (snapPage - 1) * snapPageSize,
      })
      setSnaps(page.items)
      setSnapsTotal(page.total)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }, [snapStatus, snapPage, snapPageSize])

  const loadEvents = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const page = await listEvents({
        channel: eventChannel || undefined,
        event_status: eventStatus || undefined,
        trigger_kind: trigger || undefined,
        limit: eventPageSize,
        offset: (eventPage - 1) * eventPageSize,
      })
      setEvents(page.items)
      setEventsTotal(page.total)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }, [eventChannel, eventStatus, trigger, eventPage, eventPageSize])

  useEffect(() => {
    setSnapPage(1)
  }, [snapStatus, snapPageSize])

  useEffect(() => {
    setEventPage(1)
  }, [eventChannel, eventStatus, trigger, eventPageSize])

  useEffect(() => {
    if (tab === 'snapshots') void loadSnaps()
    else void loadEvents()
  }, [tab, loadSnaps, loadEvents])

  const snapTotalPages = Math.max(1, Math.ceil(snapsTotal / snapPageSize))
  const snapCurrentPage = Math.min(snapPage, snapTotalPages)
  const snapPageStart = (snapCurrentPage - 1) * snapPageSize

  const eventTotalPages = Math.max(1, Math.ceil(eventsTotal / eventPageSize))
  const eventCurrentPage = Math.min(eventPage, eventTotalPages)
  const eventPageStart = (eventCurrentPage - 1) * eventPageSize

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
              </select>
            </label>
            <span className="run-meta">
              {snapsTotal === 0
                ? '0 건'
                : `${snapPageStart + 1}–${Math.min(snapPageStart + snapPageSize, snapsTotal)} / ${snapsTotal.toLocaleString()} 건`}
            </span>
          </div>
          <div className="table-scroll">
          <table className="grid-table">
            <thead>
              <tr>
                <th>점검 시각</th>
                <th>프로젝트.데이터셋.테이블</th>
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
                    {s.project_id ?? '(기본)'}.{s.dataset}.{s.table_name}
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
          <div className="pagination">
            <label className="filter-field">
              <span>페이지 크기</span>
              <select
                value={snapPageSize}
                onChange={(e) => setSnapPageSize(Number(e.target.value))}
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <div className="btn-row">
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setSnapPage(1)}
                disabled={snapCurrentPage <= 1 || busy}
              >
                처음
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setSnapPage((p) => Math.max(1, p - 1))}
                disabled={snapCurrentPage <= 1 || busy}
              >
                이전
              </button>
              <span className="page-indicator">
                {snapCurrentPage} / {snapTotalPages}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setSnapPage((p) => Math.min(snapTotalPages, p + 1))}
                disabled={snapCurrentPage >= snapTotalPages || busy}
              >
                다음
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setSnapPage(snapTotalPages)}
                disabled={snapCurrentPage >= snapTotalPages || busy}
              >
                마지막
              </button>
            </div>
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
              {eventsTotal === 0
                ? '0 건'
                : `${eventPageStart + 1}–${Math.min(eventPageStart + eventPageSize, eventsTotal)} / ${eventsTotal.toLocaleString()} 건`}
            </span>
          </div>
          <div className="table-scroll">
          <table className="grid-table">
            <thead>
              <tr>
                <th>발송 시각</th>
                <th>트리거</th>
                <th>채널</th>
                <th>
                  상태{' '}
                  <span className="info-tip" tabIndex={0}>
                    <span className="info-icon" aria-hidden="true">
                      ⓘ
                    </span>
                    <span className="info-tip-body" role="tooltip">
                      <strong>상태 의미</strong>
                      <ul>
                        {EVENT_STATUS_HELP.map((item) => (
                          <li key={item.label}>
                            <code>{item.label}</code> — {item.desc}
                          </li>
                        ))}
                      </ul>
                    </span>
                  </span>
                </th>
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
          <div className="pagination">
            <label className="filter-field">
              <span>페이지 크기</span>
              <select
                value={eventPageSize}
                onChange={(e) => setEventPageSize(Number(e.target.value))}
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <div className="btn-row">
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setEventPage(1)}
                disabled={eventCurrentPage <= 1 || busy}
              >
                처음
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setEventPage((p) => Math.max(1, p - 1))}
                disabled={eventCurrentPage <= 1 || busy}
              >
                이전
              </button>
              <span className="page-indicator">
                {eventCurrentPage} / {eventTotalPages}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setEventPage((p) => Math.min(eventTotalPages, p + 1))}
                disabled={eventCurrentPage >= eventTotalPages || busy}
              >
                다음
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={() => setEventPage(eventTotalPages)}
                disabled={eventCurrentPage >= eventTotalPages || busy}
              >
                마지막
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
