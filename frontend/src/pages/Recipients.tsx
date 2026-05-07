import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

import {
  createRecipient,
  deleteRecipient,
  listRecipients,
  updateRecipient,
  type Recipient,
  type RecipientCreate,
} from '../api/recipients'

const EMPTY_FORM: RecipientCreate = {
  email: '',
  name: '',
  active: true,
}

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

export function Recipients() {
  const [rows, setRows] = useState<Recipient[]>([])
  const [form, setForm] = useState<RecipientCreate>(EMPTY_FORM)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)

  const refresh = useCallback(async () => {
    setError('')
    try {
      setRows(await listRecipients())
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
      await createRecipient({
        email: form.email.trim(),
        name: form.name?.trim() || null,
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

  const onToggleActive = async (recipient: Recipient) => {
    setBusy(true)
    setError('')
    try {
      await updateRecipient(recipient.id, { active: !recipient.active })
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async (id: number) => {
    if (!window.confirm('Delete this recipient?')) return
    setBusy(true)
    setError('')
    try {
      await deleteRecipient(id)
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="tables-page">
      <h2>Alert Recipients</h2>
      {error && <p className="error">{error}</p>}

      <form className="table-form" onSubmit={onCreate}>
        <h3>Add recipient</h3>
        <div className="grid">
          <label>
            Email
            <input
              required
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="ops@example.com"
            />
          </label>
          <label>
            Name (optional)
            <input
              value={form.name ?? ''}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="DFM 운영팀"
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
            <th>Email</th>
            <th>Name</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="empty">
                no recipients registered
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.email}</td>
              <td>{r.name ?? ''}</td>
              <td>{r.active ? '✓' : ''}</td>
              <td>
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
    </section>
  )
}
