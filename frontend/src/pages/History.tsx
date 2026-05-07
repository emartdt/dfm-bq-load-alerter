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
    <section className="tables-page">
      <h2>History</h2>
      {error && <p className="error">{error}</p>}

      <nav className="tab-nav">
        <button
          type="button"
          className={tab === 'snapshots' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('snapshots')}
        >
          Check snapshots
        </button>
        <button
          type="button"
          className={tab === 'events' ? 'tab tab-active' : 'tab'}
          onClick={() => setTab('events')}
        >
          Alert events
        </button>
      </nav>

      {tab === 'snapshots' ? (
        <>
          <div className="actions">
            <label>
              Status filter{' '}
              <select
                value={snapStatus}
                onChange={(e) => setSnapStatus(e.target.value as SnapshotStatus | '')}
              >
                <option value="">(all)</option>
                <option value="ok">ok</option>
                <option value="fail">fail</option>
                <option value="insufficient_history">insufficient_history</option>
              </select>
            </label>
            <span className="run-meta">
              showing {snaps.length} / {snapsTotal}
            </span>
          </div>
          <table className="grid-table">
            <thead>
              <tr>
                <th>Checked at</th>
                <th>Dataset.Table</th>
                <th>Status</th>
                <th>Reasons</th>
                <th>Today rows</th>
                <th>Δ%</th>
              </tr>
            </thead>
            <tbody>
              {snaps.length === 0 && !busy && (
                <tr>
                  <td colSpan={6} className="empty">
                    no snapshots
                  </td>
                </tr>
              )}
              {snaps.map((s) => (
                <tr key={s.id}>
                  <td className="muted-cell">
                    {new Date(s.checked_at).toLocaleString()}
                  </td>
                  <td>
                    {s.dataset}.{s.table_name}
                  </td>
                  <td>
                    <span className={`status status-${s.status}`}>{s.status}</span>
                  </td>
                  <td className="muted-cell">{s.failure_reasons.join(', ') || '-'}</td>
                  <td className="muted-cell">
                    {s.row_count !== null ? s.row_count.toLocaleString() : '-'}
                  </td>
                  <td className="muted-cell">
                    {s.delta_percent_vs_yesterday !== null
                      ? `${s.delta_percent_vs_yesterday}%`
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <>
          <div className="actions">
            <label>
              Channel{' '}
              <select
                value={eventChannel}
                onChange={(e) => setEventChannel(e.target.value as EventChannel | '')}
              >
                <option value="">(all)</option>
                <option value="email">email</option>
                <option value="teams">teams</option>
              </select>
            </label>
            <label>
              Status{' '}
              <select
                value={eventStatus}
                onChange={(e) => setEventStatus(e.target.value as EventStatus | '')}
              >
                <option value="">(all)</option>
                <option value="sent">sent</option>
                <option value="failed">failed</option>
                <option value="skipped">skipped</option>
              </select>
            </label>
            <label>
              Trigger{' '}
              <select
                value={trigger}
                onChange={(e) => setTrigger(e.target.value as TriggerKind | '')}
              >
                <option value="">(all)</option>
                <option value="check">check</option>
                <option value="report">report</option>
              </select>
            </label>
            <span className="run-meta">
              showing {events.length} / {eventsTotal}
            </span>
          </div>
          <table className="grid-table">
            <thead>
              <tr>
                <th>Sent at</th>
                <th>Trigger</th>
                <th>Channel</th>
                <th>Status</th>
                <th>Summary</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 && !busy && (
                <tr>
                  <td colSpan={6} className="empty">
                    no events
                  </td>
                </tr>
              )}
              {events.map((e) => (
                <tr key={e.id}>
                  <td className="muted-cell">{new Date(e.sent_at).toLocaleString()}</td>
                  <td>{e.trigger_kind}</td>
                  <td>{e.channel}</td>
                  <td>
                    <span className={`status status-${e.status === 'sent' ? 'ok' : 'fail'}`}>
                      {e.status}
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
        </>
      )}
    </section>
  )
}
