import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'

import {
  createTable,
  deleteTable,
  listTables,
  reportNow,
  runNow,
  updateTable,
  type RunNowResponse,
  type TableCreate,
  type TablePatch,
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

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const
type FrequencyFilter = 'all' | 'daily' | 'monthly'
type ActiveFilter = 'all' | 'active' | 'inactive'

type SortKey =
  | 'project_id'
  | 'dataset'
  | 'table_name'
  | 'frequency'
  | 'batch_time'
  | 'buffer_minutes'
  | 'batch_day_of_month'
  | 'delta_threshold_percent'
  | 'latest_etl_row_count'
  | 'latest_etl_datetime'
  | 'note'
  | 'active'
type SortDir = 'asc' | 'desc'

function compareValues(a: unknown, b: unknown): number {
  if (a === b) return 0
  if (a === null || a === undefined) return 1
  if (b === null || b === undefined) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return a === b ? 0 : a ? -1 : 1
  return String(a).localeCompare(String(b), undefined, { numeric: true })
}

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

function rowToForm(row: TableRow): TableCreate {
  return {
    project_id: row.project_id,
    dataset: row.dataset,
    table_name: row.table_name,
    frequency: row.frequency,
    batch_time: row.batch_time.slice(0, 5),
    buffer_minutes: row.buffer_minutes,
    batch_day_of_month: row.batch_day_of_month,
    delta_threshold_percent: row.delta_threshold_percent,
    note: row.note ?? '',
    cond_buffer_load: row.cond_buffer_load,
    cond_delta_rowcount: row.cond_delta_rowcount,
    active: row.active,
  }
}

export function Tables() {
  const [rows, setRows] = useState<TableRow[]>([])
  const [form, setForm] = useState<TableCreate>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [notify, setNotify] = useState<boolean>(false)
  const [lastRun, setLastRun] = useState<RunNowResponse | null>(null)
  const formRef = useRef<HTMLFormElement | null>(null)

  const [projectQuery, setProjectQuery] = useState<string>('')
  const [datasetQuery, setDatasetQuery] = useState<string>('')
  const [tableQuery, setTableQuery] = useState<string>('')
  const [frequencyFilter, setFrequencyFilter] = useState<FrequencyFilter>('all')
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(20)

  const filteredRows = useMemo(() => {
    const pj = projectQuery.trim().toLowerCase()
    const ds = datasetQuery.trim().toLowerCase()
    const tn = tableQuery.trim().toLowerCase()
    return rows.filter((r) => {
      if (pj && !(r.project_id ?? '').toLowerCase().includes(pj)) return false
      if (ds && !r.dataset.toLowerCase().includes(ds)) return false
      if (tn && !r.table_name.toLowerCase().includes(tn)) return false
      if (frequencyFilter !== 'all' && r.frequency !== frequencyFilter) return false
      if (activeFilter === 'active' && !r.active) return false
      if (activeFilter === 'inactive' && r.active) return false
      return true
    })
  }, [rows, projectQuery, datasetQuery, tableQuery, frequencyFilter, activeFilter])

  const sortedRows = useMemo(() => {
    if (sortKey === null) return filteredRows
    const sign = sortDir === 'asc' ? 1 : -1
    return [...filteredRows].sort((a, b) => {
      const cmp = compareValues(a[sortKey], b[sortKey])
      if (cmp !== 0) return cmp * sign
      return a.id - b.id
    })
  }, [filteredRows, sortKey, sortDir])

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const pageStart = (currentPage - 1) * pageSize
  const pagedRows = sortedRows.slice(pageStart, pageStart + pageSize)

  useEffect(() => {
    setPage(1)
  }, [
    projectQuery,
    datasetQuery,
    tableQuery,
    frequencyFilter,
    activeFilter,
    sortKey,
    sortDir,
    pageSize,
  ])

  const toggleSort = (key: SortKey) => {
    if (sortKey !== key) {
      setSortKey(key)
      setSortDir('asc')
      return
    }
    if (sortDir === 'asc') {
      setSortDir('desc')
      return
    }
    setSortKey(null)
    setSortDir('asc')
  }

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return ''
    return sortDir === 'asc' ? ' ▲' : ' ▼'
  }

  const resetFilters = () => {
    setProjectQuery('')
    setDatasetQuery('')
    setTableQuery('')
    setFrequencyFilter('all')
    setActiveFilter('all')
  }
  const hasActiveFilter =
    projectQuery.trim() !== '' ||
    datasetQuery.trim() !== '' ||
    tableQuery.trim() !== '' ||
    frequencyFilter !== 'all' ||
    activeFilter !== 'all'

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

  const resetForm = () => {
    setForm(EMPTY_FORM)
    setEditingId(null)
  }

  const onEdit = (row: TableRow) => {
    setForm(rowToForm(row))
    setEditingId(row.id)
    setError('')
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const normalized = {
        project_id: form.project_id?.trim() ? form.project_id.trim() : null,
        frequency: form.frequency,
        batch_time: form.batch_time,
        buffer_minutes:
          form.buffer_minutes === null || form.buffer_minutes === undefined
            ? null
            : Number(form.buffer_minutes),
        batch_day_of_month:
          form.batch_day_of_month === null || form.batch_day_of_month === undefined
            ? null
            : Number(form.batch_day_of_month),
        delta_threshold_percent:
          form.delta_threshold_percent === null ||
          form.delta_threshold_percent === undefined
            ? null
            : Number(form.delta_threshold_percent),
        note: form.note?.trim() ? form.note.trim() : null,
        cond_buffer_load: form.cond_buffer_load ?? true,
        cond_delta_rowcount: form.cond_delta_rowcount ?? true,
        active: form.active ?? true,
      }

      if (editingId !== null) {
        const patch: TablePatch = { ...normalized }
        await updateTable(editingId, patch)
      } else {
        await createTable({
          ...normalized,
          dataset: form.dataset,
          table_name: form.table_name,
        })
      }
      resetForm()
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
      if (editingId === id) resetForm()
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

  const onReportNow = async () => {
    setBusy(true)
    setError('')
    setLastRun(null)
    try {
      setLastRun(await reportNow())
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const isEditing = editingId !== null

  return (
    <section>
      <header className="page-header">
        <h1 className="page-title">테이블</h1>
        <p className="page-subtitle">모니터링할 BigQuery 테이블과 배치 조건을 관리합니다.</p>
      </header>

      {error && <p className="error">{error}</p>}

      <form className="card" onSubmit={onSubmit} ref={formRef}>
        <h2 className="card-title">
          {isEditing ? `테이블 수정 · ${form.dataset}.${form.table_name}` : '테이블 추가'}
        </h2>
        <p className="card-subtitle">
          {isEditing
            ? '데이터셋과 테이블 이름은 식별자이므로 수정할 수 없습니다.'
            : '데이터셋·테이블·배치 시간을 입력하면 다음 cron 부터 모니터링됩니다.'}
        </p>

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
              disabled={isEditing}
              onChange={(e) => setForm({ ...form, dataset: e.target.value })}
              placeholder="bw"
            />
          </label>
          <label className="field">
            <span>테이블 이름</span>
            <input
              required
              value={form.table_name}
              disabled={isEditing}
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
              증감률 임계치 <span className="field-hint">%</span>
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
          <label className="field">
            <span>활성 여부</span>
            <select
              value={form.active ? 'true' : 'false'}
              onChange={(e) => setForm({ ...form, active: e.target.value === 'true' })}
            >
              <option value="true">활성</option>
              <option value="false">비활성</option>
            </select>
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
              전일/전월 row count 비교 (증감률)
            </label>
          </fieldset>
        </div>
        <div className="btn-row">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? '저장 중…' : isEditing ? '저장' : '추가'}
          </button>
          {isEditing && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={resetForm}
              disabled={busy}
            >
              취소
            </button>
          )}
        </div>
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
        <button
          type="button"
          className="btn btn-secondary btn-small"
          onClick={() => void onReportNow()}
          disabled={busy}
          title="07:45 일일 리포트와 동일하게 모든 활성 테이블에 대해 점검 후 이메일/Teams 발송"
        >
          지금 리포트 발송
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

      <div className="filter-bar">
        <label className="filter-field">
          <span>프로젝트</span>
          <input
            value={projectQuery}
            onChange={(e) => setProjectQuery(e.target.value)}
            placeholder="project 검색"
          />
        </label>
        <label className="filter-field">
          <span>데이터셋</span>
          <input
            value={datasetQuery}
            onChange={(e) => setDatasetQuery(e.target.value)}
            placeholder="dataset 검색"
          />
        </label>
        <label className="filter-field">
          <span>테이블</span>
          <input
            value={tableQuery}
            onChange={(e) => setTableQuery(e.target.value)}
            placeholder="table_name 검색"
          />
        </label>
        <label className="filter-field">
          <span>주기</span>
          <select
            value={frequencyFilter}
            onChange={(e) => setFrequencyFilter(e.target.value as FrequencyFilter)}
          >
            <option value="all">전체</option>
            <option value="daily">일간</option>
            <option value="monthly">월간</option>
          </select>
        </label>
        <label className="filter-field">
          <span>활성</span>
          <select
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value as ActiveFilter)}
          >
            <option value="all">전체</option>
            <option value="active">활성</option>
            <option value="inactive">비활성</option>
          </select>
        </label>
        <span className="filter-meta">
          {filteredRows.length.toLocaleString()} / {rows.length.toLocaleString()} 건
        </span>
        {hasActiveFilter && (
          <button type="button" className="btn btn-secondary btn-small" onClick={resetFilters}>
            필터 초기화
          </button>
        )}
      </div>

      <div className="table-scroll">
      <table className="grid-table">
        <thead>
          <tr>
            <th className="sortable" onClick={() => toggleSort('project_id')}>
              프로젝트{sortIndicator('project_id')}
            </th>
            <th className="sortable" onClick={() => toggleSort('dataset')}>
              데이터셋{sortIndicator('dataset')}
            </th>
            <th className="sortable" onClick={() => toggleSort('table_name')}>
              테이블{sortIndicator('table_name')}
            </th>
            <th className="sortable" onClick={() => toggleSort('frequency')}>
              주기{sortIndicator('frequency')}
            </th>
            <th className="sortable" onClick={() => toggleSort('batch_time')}>
              배치{sortIndicator('batch_time')}
            </th>
            <th className="sortable" onClick={() => toggleSort('buffer_minutes')}>
              버퍼(분){sortIndicator('buffer_minutes')}
            </th>
            <th className="sortable" onClick={() => toggleSort('batch_day_of_month')}>
              월일{sortIndicator('batch_day_of_month')}
            </th>
            <th className="sortable" onClick={() => toggleSort('delta_threshold_percent')}>
              증감률{sortIndicator('delta_threshold_percent')}
            </th>
            <th className="sortable" onClick={() => toggleSort('latest_etl_row_count')}>
              최근 ETL row count{sortIndicator('latest_etl_row_count')}
            </th>
            <th className="sortable" onClick={() => toggleSort('latest_etl_datetime')}>
              최근 ETL 시각{sortIndicator('latest_etl_datetime')}
            </th>
            <th className="sortable" onClick={() => toggleSort('note')}>
              메모{sortIndicator('note')}
            </th>
            <th className="sortable" onClick={() => toggleSort('active')}>
              활성{sortIndicator('active')}
            </th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {pagedRows.length === 0 && (
            <tr>
              <td colSpan={13} className="empty">
                {rows.length === 0
                  ? '등록된 테이블이 없습니다.'
                  : '필터 조건과 일치하는 테이블이 없습니다.'}
              </td>
            </tr>
          )}
          {pagedRows.map((r) => (
            <tr key={r.id} className={editingId === r.id ? 'selected-row' : undefined}>
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
              <td className="muted-cell">
                {r.latest_etl_datetime === null
                  ? '—'
                  : new Date(r.latest_etl_datetime).toLocaleString()}
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
                    className="btn btn-secondary btn-small"
                    onClick={() => onEdit(r)}
                    disabled={busy}
                  >
                    수정
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
      </div>

      <div className="pagination">
        <label className="filter-field">
          <span>페이지 크기</span>
          <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <span className="filter-meta">
          {filteredRows.length === 0
            ? '0 건'
            : `${pageStart + 1}–${Math.min(pageStart + pageSize, filteredRows.length)} / ${filteredRows.length.toLocaleString()} 건`}
        </span>
        <div className="btn-row">
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => setPage(1)}
            disabled={currentPage <= 1}
          >
            처음
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
          >
            이전
          </button>
          <span className="page-indicator">
            {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
          >
            다음
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => setPage(totalPages)}
            disabled={currentPage >= totalPages}
          >
            마지막
          </button>
        </div>
      </div>

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
                  <> · 증감률={s.delta_percent_vs_yesterday}%</>
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
