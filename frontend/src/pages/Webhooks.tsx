import { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'

import {
  createWebhook,
  deleteWebhook,
  listWebhooks,
  testWebhook,
  updateWebhook,
  type Webhook,
  type WebhookCreate,
  type WebhookTestResult,
} from '../api/webhooks'

const EMPTY_FORM: WebhookCreate = {
  name: '',
  webhook_url: '',
  active: true,
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const
type ActiveFilter = 'all' | 'active' | 'inactive'
type SortKey = 'name' | 'webhook_url_masked' | 'active'
type SortDir = 'asc' | 'desc'

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

function compareValues(a: unknown, b: unknown): number {
  if (a === b) return 0
  if (a === null || a === undefined) return 1
  if (b === null || b === undefined) return -1
  if (typeof a === 'boolean' && typeof b === 'boolean') return a === b ? 0 : a ? -1 : 1
  return String(a).localeCompare(String(b), undefined, { numeric: true })
}

export function Webhooks() {
  const [rows, setRows] = useState<Webhook[]>([])
  const [form, setForm] = useState<WebhookCreate>(EMPTY_FORM)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [testResult, setTestResult] = useState<{ id: number; result: WebhookTestResult } | null>(
    null,
  )

  const [query, setQuery] = useState<string>('')
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(20)

  const refresh = useCallback(async () => {
    setError('')
    try {
      setRows(await listWebhooks())
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((r) => {
      if (q) {
        const hay = `${r.name} ${r.webhook_url_masked ?? ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (activeFilter === 'active' && !r.active) return false
      if (activeFilter === 'inactive' && r.active) return false
      return true
    })
  }, [rows, query, activeFilter])

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
  }, [query, activeFilter, sortKey, sortDir, pageSize])

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

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await createWebhook({
        name: form.name.trim(),
        webhook_url: form.webhook_url.trim(),
        active: form.active ?? true,
      })
      setForm(EMPTY_FORM)
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onToggleActive = async (hook: Webhook) => {
    setBusy(true)
    setError('')
    try {
      await updateWebhook(hook.id, { active: !hook.active })
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async (id: number) => {
    if (!window.confirm('이 웹훅을 삭제할까요?')) return
    setBusy(true)
    setError('')
    try {
      await deleteWebhook(id)
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onTest = async (id: number) => {
    setBusy(true)
    setError('')
    setTestResult(null)
    try {
      const result = await testWebhook(id)
      setTestResult({ id, result })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const hasActiveFilter = query.trim() !== '' || activeFilter !== 'all'

  return (
    <section>
      <header className="page-header">
        <h1 className="page-title">Teams 웹훅</h1>
        <p className="page-subtitle">Microsoft Teams 채널로 알림을 보낼 incoming webhook URL을 등록합니다.</p>
      </header>

      {error && <p className="error">{error}</p>}

      <form className="card" onSubmit={onCreate}>
        <h2 className="card-title">웹훅 추가</h2>
        <div className="form-grid">
          <label className="field">
            <span>이름</span>
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="ops-room"
            />
          </label>
          <label className="field span-2">
            <span>웹훅 URL</span>
            <input
              required
              type="url"
              value={form.webhook_url}
              onChange={(e) => setForm({ ...form, webhook_url: e.target.value })}
              placeholder="https://outlook.office.com/webhook/..."
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
        </div>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? '저장 중…' : '추가'}
        </button>
      </form>

      <div className="filter-bar">
        <label className="filter-field">
          <span>검색</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="이름·URL 검색"
          />
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
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => {
              setQuery('')
              setActiveFilter('all')
            }}
          >
            필터 초기화
          </button>
        )}
      </div>

      <div className="table-scroll">
      <table className="grid-table">
        <thead>
          <tr>
            <th className="sortable" onClick={() => toggleSort('name')}>
              이름{sortIndicator('name')}
            </th>
            <th className="sortable" onClick={() => toggleSort('webhook_url_masked')}>
              URL (마스킹){sortIndicator('webhook_url_masked')}
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
              <td colSpan={4} className="empty">
                {rows.length === 0
                  ? '등록된 웹훅이 없습니다.'
                  : '필터 조건과 일치하는 웹훅이 없습니다.'}
              </td>
            </tr>
          )}
          {pagedRows.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td className="muted-cell">{r.webhook_url_masked || '—'}</td>
              <td>{r.active ? '✓' : ''}</td>
              <td>
                <div className="btn-row">
                  <button
                    className="btn btn-secondary btn-small"
                    onClick={() => void onTest(r.id)}
                    disabled={busy}
                  >
                    테스트
                  </button>
                  <button
                    className="btn btn-secondary btn-small"
                    onClick={() => void onToggleActive(r)}
                    disabled={busy}
                  >
                    {r.active ? '비활성화' : '활성화'}
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

      {testResult && (
        <p className={`run-meta status status-${testResult.result.ok ? 'ok' : 'fail'}`}>
          웹훅 #{testResult.id} → {testResult.result.ok ? '성공' : '실패'} · {testResult.result.detail}
        </p>
      )}
    </section>
  )
}
