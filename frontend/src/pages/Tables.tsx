import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

import {
  createTable,
  deleteTable,
  listTables,
  runNow,
  type RunNowResponse,
  type TableCreate,
  type TableRow,
} from '../api/tables'

const EMPTY_FORM: TableCreate = {
  dataset: '',
  table_name: '',
  frequency: 'daily',
  batch_time: '05:00',
  deadline_time: '09:00',
  batch_day_of_month: null,
  delta_threshold_percent: null,
  active: true,
}

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

export function Tables() {
  const [rows, setRows] = useState<TableRow[]>([])
  const [form, setForm] = useState<TableCreate>(EMPTY_FORM)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [notify, setNotify] = useState<boolean>(false)
  const [lastRun, setLastRun] = useState<RunNowResponse | null>(null)

  const refresh = useCallback(async () => {
    setError('')
    try {
      setRows(await listTables())
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await createTable({
        ...form,
        delta_threshold_percent:
          form.delta_threshold_percent === null ||
          form.delta_threshold_percent === undefined
            ? null
            : Number(form.delta_threshold_percent),
        batch_day_of_month:
          form.batch_day_of_month === null || form.batch_day_of_month === undefined
            ? null
            : Number(form.batch_day_of_month),
      })
      setForm(EMPTY_FORM)
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async (id: number) => {
    if (!window.confirm('Delete this table?')) return
    setBusy(true)
    setError('')
    try {
      await deleteTable(id)
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onRunNow = async (tableId?: number) => {
    setBusy(true)
    setError('')
    setLastRun(null)
    try {
      setLastRun(await runNow(tableId, notify))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="tables-page">
      <h2>Tables</h2>
      {error && <p className="error">{error}</p>}

      <form className="table-form" onSubmit={onCreate}>
        <h3>Add table</h3>
        <div className="grid">
          <label>
            Dataset
            <input
              required
              value={form.dataset}
              onChange={(e) => setForm({ ...form, dataset: e.target.value })}
              placeholder="bw"
            />
          </label>
          <label>
            Table name
            <input
              required
              value={form.table_name}
              onChange={(e) => setForm({ ...form, table_name: e.target.value })}
              placeholder="PZEVENTID"
            />
          </label>
          <label>
            Frequency
            <select
              value={form.frequency}
              onChange={(e) =>
                setForm({ ...form, frequency: e.target.value as 'daily' | 'monthly' })
              }
            >
              <option value="daily">daily</option>
              <option value="monthly">monthly</option>
            </select>
          </label>
          <label>
            Batch time (KST)
            <input
              type="time"
              required
              value={form.batch_time}
              onChange={(e) => setForm({ ...form, batch_time: e.target.value })}
            />
          </label>
          <label>
            Deadline time (KST)
            <input
              type="time"
              required
              value={form.deadline_time}
              onChange={(e) => setForm({ ...form, deadline_time: e.target.value })}
            />
          </label>
          {form.frequency === 'monthly' && (
            <label>
              Batch day of month
              <input
                type="number"
                min={1}
                max={31}
                value={form.batch_day_of_month ?? ''}
                onChange={(e) =>
                  setForm({
                    ...form,
                    batch_day_of_month: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          )}
          <label>
            Delta threshold %
            <input
              type="number"
              min={0}
              max={100}
              step={0.1}
              value={form.delta_threshold_percent ?? ''}
              onChange={(e) =>
                setForm({
                  ...form,
                  delta_threshold_percent:
                    e.target.value === '' ? null : Number(e.target.value),
                })
              }
              placeholder="default 25"
            />
          </label>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Add'}
        </button>
      </form>

      <div className="actions">
        <button type="button" onClick={() => void onRunNow()} disabled={busy}>
          Run now (all)
        </button>
        <label className="notify-toggle">
          <input
            type="checkbox"
            checked={notify}
            onChange={(e) => setNotify(e.target.checked)}
          />
          Send alerts (이메일 + Teams)
        </label>
        {lastRun && (
          <span className="run-meta">
            sent_events={lastRun.sent_events} (notified={String(lastRun.notified)})
          </span>
        )}
      </div>

      <table className="grid-table">
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Table</th>
            <th>Freq</th>
            <th>Batch</th>
            <th>Deadline</th>
            <th>DOM</th>
            <th>Δ%</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={9} className="empty">
                no tables registered
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.dataset}</td>
              <td>{r.table_name}</td>
              <td>{r.frequency}</td>
              <td>{r.batch_time}</td>
              <td>{r.deadline_time}</td>
              <td>{r.batch_day_of_month ?? ''}</td>
              <td>{r.delta_threshold_percent ?? '(default)'}</td>
              <td>{r.active ? '✓' : ''}</td>
              <td>
                <button onClick={() => void onRunNow(r.id)} disabled={busy}>
                  Run
                </button>
                <button onClick={() => void onDelete(r.id)} disabled={busy}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {lastRun && (
        <section className="run-result">
          <h3>Last run @ {new Date(lastRun.triggered_at).toLocaleString()}</h3>
          <p>{lastRun.snapshot_count} snapshot(s)</p>
          <ul>
            {lastRun.snapshots.map((s, i) => (
              <li key={i}>
                table_id={s.table_id} · status=
                <span className={`status status-${s.status}`}>{s.status}</span>
                {s.row_count !== null && <> · rows={s.row_count.toLocaleString()}</>}
                {s.delta_percent_vs_yesterday !== null && (
                  <> · Δ={s.delta_percent_vs_yesterday}%</>
                )}
                {s.failure_reasons.length > 0 && (
                  <> · reasons=[{s.failure_reasons.join(', ')}]</>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  )
}
