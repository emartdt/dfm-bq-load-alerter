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
    if (!window.confirm('이 수신자를 삭제할까요?')) return
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
    <section>
      <header className="page-header">
        <h1 className="page-title">알림 수신자</h1>
        <p className="page-subtitle">이메일 알림을 받는 운영자 명단을 관리합니다.</p>
      </header>

      {error && <p className="error">{error}</p>}

      <form className="card" onSubmit={onCreate}>
        <h2 className="card-title">수신자 추가</h2>
        <div className="form-grid">
          <label className="field">
            <span>이메일</span>
            <input
              required
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="ops@example.com"
            />
          </label>
          <label className="field">
            <span>
              이름 <span className="field-hint">(선택)</span>
            </span>
            <input
              value={form.name ?? ''}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="DFM 운영팀"
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

      <table className="grid-table">
        <thead>
          <tr>
            <th>이메일</th>
            <th>이름</th>
            <th>활성</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="empty">
                등록된 수신자가 없습니다.
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.email}</td>
              <td>{r.name ?? ''}</td>
              <td>{r.active ? '✓' : ''}</td>
              <td>
                <div className="btn-row">
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
    </section>
  )
}
