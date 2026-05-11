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
  project_id: null,
  dataset: '',
  table_name: '',
  frequency: 'daily',
  batch_time: '05:00',
  buffer_minutes: null,
  batch_day_of_month: null,
  delta_threshold_percent: null,
  note: '',
  cond_buffer_load: true,
  cond_delta_rowcount: true,
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
        project_id: form.project_id?.trim() ? form.project_id.trim() : null,
        delta_threshold_percent:
          form.delta_threshold_percent === null ||
          form.delta_threshold_percent === undefined
            ? null
            : Number(form.delta_threshold_percent),
        batch_day_of_month:
          form.batch_day_of_month === null || form.batch_day_of_month === undefined
            ? null
            : Number(form.batch_day_of_month),
        note: form.note?.trim() ? form.note.trim() : null,
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
            Project ID (빈 값=환경 기본)
            <input
              value={form.project_id ?? ''}
              onChange={(e) =>
                setForm({
                  ...form,
                  project_id: e.target.value === '' ? null : e.target.value,
                })
              }
              placeholder="emart-datafabric"
            />
          </label>
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
            Buffer (분; 빈 값=정책 기본)
            <input
              type="number"
              min={1}
              max={1440}
              value={form.buffer_minutes ?? ''}
              onChange={(e) =>
                setForm({
                  ...form,
                  buffer_minutes: e.target.value === '' ? null : Number(e.target.value),
                })
              }
              placeholder="default 30"
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
          <label className="span-2">
            Note (운영 메모; 알림 본문에 노출)
            <input
              value={form.note ?? ''}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder="월말 결산 BW · ETL 작업자: data-platform"
            />
          </label>
          <fieldset className="span-2 cond-toggles">
            <legend>알람 조건 (OR)</legend>
            <label className="inline">
              <input
                type="checkbox"
                checked={form.cond_buffer_load ?? true}
                onChange={(e) =>
                  setForm({ ...form, cond_buffer_load: e.target.checked })
                }
              />
              버퍼 시간 내 적재 + ROW COUNT=0
            </label>
            <label className="inline">
              <input
                type="checkbox"
                checked={form.cond_delta_rowcount ?? true}
                onChange={(e) =>
                  setForm({ ...form, cond_delta_rowcount: e.target.checked })
                }
              />
              전일/전월 row count 비교 (Δ%)
            </label>
          </fieldset>
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
            <th>Project</th>
            <th>Dataset</th>
            <th>Table</th>
            <th>Freq</th>
            <th>Batch</th>
            <th>Buffer(분)</th>
            <th>DOM</th>
            <th>Δ%</th>
            <th>최근 ETL row count</th>
            <th>Note</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={12} className="empty">
                no tables registered
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="muted-cell" title={r.project_id ?? ''}>
                {r.project_id ?? '(default)'}
              </td>
              <td>{r.dataset}</td>
              <td>{r.table_name}</td>
              <td>{r.frequency}</td>
              <td>{r.batch_time}</td>
              <td>{r.buffer_minutes ?? '(default)'}</td>
              <td>{r.batch_day_of_month ?? ''}</td>
              <td>{r.delta_threshold_percent ?? '(default)'}</td>
              <td className="numeric-cell">
                {r.latest_etl_row_count === null
                  ? '—'
                  : r.latest_etl_row_count.toLocaleString()}
              </td>
              <td className="muted-cell" title={r.note ?? ''}>
                {r.note && r.note.length > 24 ? `${r.note.slice(0, 24)}…` : r.note ?? ''}
              </td>
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
