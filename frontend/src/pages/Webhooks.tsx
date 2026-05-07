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
    if (!window.confirm('Delete this webhook?')) return
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
    <section className="tables-page">
      <h2>Teams Webhooks</h2>
      {error && <p className="error">{error}</p>}

      <form className="table-form" onSubmit={onCreate}>
        <h3>Add webhook</h3>
        <div className="grid">
          <label>
            Name
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="ops-room"
            />
          </label>
          <label>
            Webhook URL
            <input
              required
              type="url"
              value={form.webhook_url}
              onChange={(e) => setForm({ ...form, webhook_url: e.target.value })}
              placeholder="https://outlook.office.com/webhook/..."
            />
          </label>
          <label>
            Active
            <select
              value={form.active ? 'true' : 'false'}
              onChange={(e) => setForm({ ...form, active: e.target.value === 'true' })}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Add'}
        </button>
      </form>

      <table className="grid-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>URL (masked)</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="empty">
                no webhooks registered
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td className="muted-cell">{r.webhook_url_masked || '—'}</td>
              <td>{r.active ? '✓' : ''}</td>
              <td>
                <button onClick={() => void onTest(r.id)} disabled={busy}>
                  Test
                </button>
                <button onClick={() => void onToggleActive(r)} disabled={busy}>
                  {r.active ? 'Deactivate' : 'Activate'}
                </button>
                <button onClick={() => void onDelete(r.id)} disabled={busy}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {testResult && (
        <p className={`run-meta ${testResult.result.ok ? 'status-ok' : 'status-fail'}`}>
          test webhook id={testResult.id} → {testResult.result.ok ? 'OK' : 'FAILED'} ·{' '}
          {testResult.result.detail}
        </p>
      )}
    </section>
  )
}
