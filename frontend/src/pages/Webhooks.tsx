import { useCallback, useEffect, useState } from 'react'
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

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

export function Webhooks() {
  const [rows, setRows] = useState<Webhook[]>([])
  const [form, setForm] = useState<WebhookCreate>(EMPTY_FORM)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [testResult, setTestResult] = useState<{ id: number; result: WebhookTestResult } | null>(
    null,
  )

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

      <div className="table-scroll">
      <table className="grid-table">
        <thead>
          <tr>
            <th>이름</th>
            <th>URL (마스킹)</th>
            <th>활성</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="empty">
                등록된 웹훅이 없습니다.
              </td>
            </tr>
          )}
          {rows.map((r) => (
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

      {testResult && (
        <p className={`run-meta status status-${testResult.result.ok ? 'ok' : 'fail'}`}>
          웹훅 #{testResult.id} → {testResult.result.ok ? '성공' : '실패'} · {testResult.result.detail}
        </p>
      )}
    </section>
  )
}
