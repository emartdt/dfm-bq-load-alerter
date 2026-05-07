import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

import { listGroups, type Group } from '../api/groups'
import {
  createTable,
  deleteTable,
  listTables,
  runNow,
  updateTable,
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
  note: '',
  group_id: null,
  cond_buffer_load: true,
  cond_delta_rowcount: true,
  cond_inflow_time_drift: false,
  inflow_drift_threshold_minutes: null,
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
  const [groups, setGroups] = useState<Group[]>([])
  const [form, setForm] = useState<TableCreate>(EMPTY_FORM)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [notify, setNotify] = useState<boolean>(false)
  const [lastRun, setLastRun] = useState<RunNowResponse | null>(null)

  const refresh = useCallback(async () => {
    setError('')
    try {
      const [t, g] = await Promise.all([listTables(), listGroups()])
      setRows(t)
      setGroups(g)
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  const onChangeGroup = async (id: number, group_id: number | null) => {
    setBusy(true)
    setError('')
    try {
      await updateTable(id, { group_id })
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const groupName = (id: number | null | undefined): string =>
    id ? groups.find((g) => g.id === id)?.name ?? `#${id}` : '(global)'

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
          <label>
            Alert group
            <select
              value={form.group_id ?? ''}
              onChange={(e) =>
                setForm({
                  ...form,
                  group_id: e.target.value === '' ? null : Number(e.target.value),
                })
              }
            >
              <option value="">(global default)</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
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
            <label className="inline">
              <input
                type="checkbox"
                checked={form.cond_inflow_time_drift ?? false}
                onChange={(e) =>
                  setForm({ ...form, cond_inflow_time_drift: e.target.checked })
                }
              />
              유입 시간 비교
            </label>
            {form.cond_inflow_time_drift && (
              <label className="inline">
                drift 임계치 (분; 빈 값=정책 기본):
                <input
                  type="number"
                  min={1}
                  max={1440}
                  value={form.inflow_drift_threshold_minutes ?? ''}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      inflow_drift_threshold_minutes:
                        e.target.value === '' ? null : Number(e.target.value),
                    })
                  }
                />
              </label>
            )}
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
            <th>Dataset</th>
            <th>Table</th>
            <th>Freq</th>
            <th>Batch</th>
            <th>Deadline</th>
            <th>DOM</th>
            <th>Δ%</th>
            <th>Group</th>
            <th>Note</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={11} className="empty">
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
              <td>
                <select
                  value={r.group_id ?? ''}
                  disabled={busy}
                  onChange={(e) =>
                    void onChangeGroup(
                      r.id,
                      e.target.value === '' ? null : Number(e.target.value),
                    )
                  }
                  title={groupName(r.group_id)}
                >
                  <option value="">(global)</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
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
