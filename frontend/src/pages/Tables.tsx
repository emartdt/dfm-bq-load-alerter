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

const STATUS_LABEL: Record<string, string> = {
  ok: '정상',
  fail: '실패',
  insufficient_history: '이력 부족',
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
    if (!window.confirm('이 테이블을 삭제할까요?')) return
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
    <section>
      <header className="page-header">
        <h1 className="page-title">테이블</h1>
        <p className="page-subtitle">모니터링할 BigQuery 테이블과 배치 조건을 관리합니다.</p>
      </header>

      {error && <p className="error">{error}</p>}

      <form className="card" onSubmit={onCreate}>
        <h2 className="card-title">테이블 추가</h2>
        <p className="card-subtitle">데이터셋·테이블·배치 시간을 입력하면 다음 cron 부터 모니터링됩니다.</p>

        <div className="form-grid">
          <label className="field">
            <span>
              프로젝트 ID <span className="field-hint">(빈 값 = 환경 기본)</span>
            </span>
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
          <label className="field">
            <span>데이터셋</span>
            <input
              required
              value={form.dataset}
              onChange={(e) => setForm({ ...form, dataset: e.target.value })}
              placeholder="bw"
            />
          </label>
          <label className="field">
            <span>테이블 이름</span>
            <input
              required
              value={form.table_name}
              onChange={(e) => setForm({ ...form, table_name: e.target.value })}
              placeholder="PZEVENTID"
            />
          </label>
          <label className="field">
            <span>주기</span>
            <select
              value={form.frequency}
              onChange={(e) =>
                setForm({ ...form, frequency: e.target.value as 'daily' | 'monthly' })
              }
            >
              <option value="daily">일간</option>
              <option value="monthly">월간</option>
            </select>
          </label>
          <label className="field">
            <span>배치 시각 (KST)</span>
            <input
              type="time"
              required
              value={form.batch_time}
              onChange={(e) => setForm({ ...form, batch_time: e.target.value })}
            />
          </label>
          <label className="field">
            <span>
              버퍼 (분) <span className="field-hint">빈 값 = 정책 기본</span>
            </span>
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
              placeholder="기본 30"
            />
          </label>
          {form.frequency === 'monthly' && (
            <label className="field">
              <span>월 배치일</span>
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
          <label className="field">
            <span>
              증감 임계치 <span className="field-hint">%</span>
            </span>
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
              placeholder="기본 25"
            />
          </label>
          <label className="field span-2">
            <span>
              메모 <span className="field-hint">운영 메모, 알림 본문에 노출</span>
            </span>
            <input
              value={form.note ?? ''}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder="월말 결산 BW · ETL 작업자: data-platform"
            />
          </label>
          <fieldset className="cond-toggles span-2">
            <legend>알람 조건 (OR)</legend>
            <label className="inline">
              <input
                type="checkbox"
                checked={form.cond_buffer_load ?? true}
                onChange={(e) =>
                  setForm({ ...form, cond_buffer_load: e.target.checked })
                }
              />
              버퍼 시간 내 적재 + ROW COUNT = 0
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
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? '저장 중…' : '추가'}
        </button>
      </form>

      <div className="actions">
        <button
          type="button"
          className="btn btn-secondary btn-small"
          onClick={() => void onRunNow()}
          disabled={busy}
        >
          전체 즉시 실행
        </button>
        <label className="notify-toggle">
          <input
            type="checkbox"
            checked={notify}
            onChange={(e) => setNotify(e.target.checked)}
          />
          알림 전송 (이메일 + Teams)
        </label>
        {lastRun && (
          <span className="run-meta">
            전송 이벤트 {lastRun.sent_events}건 · 알림 {lastRun.notified ? '발송' : '미발송'}
          </span>
        )}
      </div>

      <table className="grid-table">
        <thead>
          <tr>
            <th>프로젝트</th>
            <th>데이터셋</th>
            <th>테이블</th>
            <th>주기</th>
            <th>배치</th>
            <th>버퍼(분)</th>
            <th>월일</th>
            <th>Δ%</th>
            <th>최근 ETL row count</th>
            <th>메모</th>
            <th>활성</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={12} className="empty">
                등록된 테이블이 없습니다.
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="muted-cell" title={r.project_id ?? ''}>
                {r.project_id ?? '(기본)'}
              </td>
              <td>{r.dataset}</td>
              <td>{r.table_name}</td>
              <td>{r.frequency === 'daily' ? '일간' : '월간'}</td>
              <td>{r.batch_time}</td>
              <td>{r.buffer_minutes ?? '(기본)'}</td>
              <td>{r.batch_day_of_month ?? ''}</td>
              <td>{r.delta_threshold_percent ?? '(기본)'}</td>
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
                <div className="btn-row">
                  <button
                    className="btn btn-secondary btn-small"
                    onClick={() => void onRunNow(r.id)}
                    disabled={busy}
                  >
                    실행
                  </button>
                  <button
                    className="btn btn-danger btn-small"
                    onClick={() => void onDelete(r.id)}
                    disabled={busy}
                  >
                    삭제
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {lastRun && (
        <section className="run-result">
          <h3>최근 실행 — {new Date(lastRun.triggered_at).toLocaleString()}</h3>
          <p className="run-meta">스냅샷 {lastRun.snapshot_count}건</p>
          <ul>
            {lastRun.snapshots.map((s, i) => (
              <li key={i}>
                table_id={s.table_id} · 상태=
                <span className={`status status-${s.status}`}>
                  {STATUS_LABEL[s.status] ?? s.status}
                </span>
                {s.row_count !== null && <> · rows={s.row_count.toLocaleString()}</>}
                {s.delta_percent_vs_yesterday !== null && (
                  <> · Δ={s.delta_percent_vs_yesterday}%</>
                )}
                {s.failure_reasons.length > 0 && (
                  <> · 사유=[{s.failure_reasons.join(', ')}]</>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  )
}
