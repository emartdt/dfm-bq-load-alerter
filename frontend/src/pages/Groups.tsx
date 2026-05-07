import { useCallback, useEffect, useMemo, useState } from 'react'
import axios from 'axios'

import {
  createGroup,
  deleteGroup,
  listGroupRecipients,
  listGroupTables,
  listGroupWebhooks,
  listGroups,
  setGroupRecipients,
  setGroupTables,
  setGroupWebhooks,
  type Group,
  type GroupCreate,
} from '../api/groups'
import { listRecipients, type Recipient } from '../api/recipients'
import { listTables, type TableRow } from '../api/tables'
import { listWebhooks, type Webhook } from '../api/webhooks'

const EMPTY_FORM: GroupCreate = { name: '', description: '', active: true }

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

export function Groups() {
  const [groups, setGroups] = useState<Group[]>([])
  const [recipients, setRecipients] = useState<Recipient[]>([])
  const [webhooks, setWebhooks] = useState<Webhook[]>([])
  const [tables, setTables] = useState<TableRow[]>([])
  const [form, setForm] = useState<GroupCreate>(EMPTY_FORM)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [selected, setSelected] = useState<Group | null>(null)
  const [memberRecipients, setMemberRecipients] = useState<Set<number>>(new Set())
  const [memberWebhooks, setMemberWebhooks] = useState<Set<number>>(new Set())
  const [memberTables, setMemberTables] = useState<Set<number>>(new Set())
  const [savedNote, setSavedNote] = useState<string>('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const [g, r, w, t] = await Promise.all([
        listGroups(),
        listRecipients(),
        listWebhooks(),
        listTables(),
      ])
      setGroups(g)
      setRecipients(r)
      setWebhooks(w)
      setTables(t)
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const loadMembers = useCallback(async (group: Group) => {
    setError('')
    setSavedNote('')
    try {
      const [rIds, wIds, tIds] = await Promise.all([
        listGroupRecipients(group.id),
        listGroupWebhooks(group.id),
        listGroupTables(group.id),
      ])
      setMemberRecipients(new Set(rIds))
      setMemberWebhooks(new Set(wIds))
      setMemberTables(new Set(tIds))
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  const onSelect = async (g: Group) => {
    setSelected(g)
    await loadMembers(g)
  }

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await createGroup({
        name: form.name.trim(),
        description: form.description?.trim() || null,
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

  const onDelete = async (g: Group) => {
    if (!window.confirm(`Delete group "${g.name}"? Member tables revert to global default.`))
      return
    setBusy(true)
    setError('')
    try {
      await deleteGroup(g.id)
      if (selected?.id === g.id) setSelected(null)
      await refresh()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const toggle = (set: Set<number>, id: number) => {
    const next = new Set(set)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  }

  const onSaveMembers = async () => {
    if (!selected) return
    setBusy(true)
    setError('')
    setSavedNote('')
    try {
      await Promise.all([
        setGroupRecipients(selected.id, [...memberRecipients]),
        setGroupWebhooks(selected.id, [...memberWebhooks]),
        setGroupTables(selected.id, [...memberTables]),
      ])
      setSavedNote(`saved members for ${selected.name}`)
      await refresh()
      // refresh selected group counts from list
      const updated = (await listGroups()).find((g) => g.id === selected.id)
      if (updated) setSelected(updated)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const tableLabel = useMemo(
    () => (id: number) => {
      const t = tables.find((x) => x.id === id)
      return t ? `${t.dataset}.${t.table_name}` : `#${id}`
    },
    [tables],
  )

  return (
    <section className="tables-page">
      <h2>Alert Groups</h2>
      {error && <p className="error">{error}</p>}

      <form className="table-form" onSubmit={onCreate}>
        <h3>Add group</h3>
        <div className="grid">
          <label>
            Name
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="data-platform-onCall"
            />
          </label>
          <label>
            Description
            <input
              value={form.description ?? ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="DataPlatform 팀 일/월 적재 모니터링"
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
            <th>Description</th>
            <th>Tables</th>
            <th>Recipients</th>
            <th>Webhooks</th>
            <th>Active</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {groups.length === 0 && (
            <tr>
              <td colSpan={7} className="empty">
                no groups
              </td>
            </tr>
          )}
          {groups.map((g) => (
            <tr key={g.id} className={selected?.id === g.id ? 'selected-row' : undefined}>
              <td>{g.name}</td>
              <td>{g.description ?? ''}</td>
              <td>{g.table_count}</td>
              <td>{g.recipient_count}</td>
              <td>{g.webhook_count}</td>
              <td>{g.active ? '✓' : ''}</td>
              <td>
                <button onClick={() => void onSelect(g)} disabled={busy}>
                  Edit members
                </button>
                <button onClick={() => void onDelete(g)} disabled={busy}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <section className="run-result">
          <h3>
            Members of <em>{selected.name}</em>
          </h3>
          {savedNote && <p className="muted-cell">{savedNote}</p>}

          <div className="member-grid">
            <div>
              <h4>Recipients</h4>
              {recipients.length === 0 ? (
                <p className="empty">no recipients yet — add one in /recipients</p>
              ) : (
                <ul className="checklist">
                  {recipients.map((r) => (
                    <li key={r.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={memberRecipients.has(r.id)}
                          onChange={() =>
                            setMemberRecipients((s) => toggle(s, r.id))
                          }
                        />{' '}
                        {r.email}
                        {r.name ? ` (${r.name})` : ''}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <h4>Webhooks</h4>
              {webhooks.length === 0 ? (
                <p className="empty">no webhooks yet — add one in /webhooks</p>
              ) : (
                <ul className="checklist">
                  {webhooks.map((w) => (
                    <li key={w.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={memberWebhooks.has(w.id)}
                          onChange={() => setMemberWebhooks((s) => toggle(s, w.id))}
                        />{' '}
                        {w.name}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <h4>Tables</h4>
              {tables.length === 0 ? (
                <p className="empty">no tables yet — add one in /tables</p>
              ) : (
                <ul className="checklist">
                  {tables.map((t) => (
                    <li key={t.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={memberTables.has(t.id)}
                          onChange={() => setMemberTables((s) => toggle(s, t.id))}
                        />{' '}
                        {tableLabel(t.id)}
                        {t.group_id && t.group_id !== selected.id && (
                          <span className="muted-cell"> (currently in group #{t.group_id})</span>
                        )}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <button type="button" onClick={() => void onSaveMembers()} disabled={busy}>
            {busy ? 'Saving…' : 'Save members'}
          </button>{' '}
          <button type="button" onClick={() => setSelected(null)} disabled={busy}>
            Close
          </button>
        </section>
      )}
    </section>
  )
}
