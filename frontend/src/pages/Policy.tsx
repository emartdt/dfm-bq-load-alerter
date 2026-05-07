import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'

import { getPolicy, updatePolicy, type Policy } from '../api/policy'

function describeError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    return detail ? `${err.response?.status}: ${JSON.stringify(detail)}` : err.message
  }
  return err instanceof Error ? err.message : String(err)
}

export function PolicyPage() {
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [error, setError] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [savedNote, setSavedNote] = useState<string>('')

  const [checkTimes, setCheckTimes] = useState<string>('')
  const [reportTime, setReportTime] = useState<string>('07:45')
  const [defaultThreshold, setDefaultThreshold] = useState<string>('25')
  const [retentionDays, setRetentionDays] = useState<string>('90')
  const [conditionMaxBytes, setConditionMaxBytes] = useState<string>('104857600')
  const [dedupStrategy, setDedupStrategy] = useState<string>('every-hour-resend')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const p = await getPolicy()
      setPolicy(p)
      setCheckTimes(p.check_times.join(', '))
      setReportTime(p.report_time.slice(0, 5))
      setDefaultThreshold(String(p.default_threshold_percent))
      setRetentionDays(String(p.retention_days))
      setConditionMaxBytes(String(p.condition_query_max_bytes))
      setDedupStrategy(p.dedup_strategy)
    } catch (err) {
      setError(describeError(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setSavedNote('')
    try {
      const updated = await updatePolicy({
        check_times: checkTimes
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        report_time: reportTime,
        default_threshold_percent: Number(defaultThreshold),
        retention_days: Number(retentionDays),
        condition_query_max_bytes: Number(conditionMaxBytes),
        dedup_strategy: dedupStrategy,
      })
      setPolicy(updated)
      setSavedNote(`saved at ${new Date(updated.updated_at).toLocaleString()}`)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="tables-page">
      <h2>Alert Policy</h2>
      <p className="muted-cell">
        시스템 전역 정책 (singleton). 변경 사항은 다음 cron 부터 적용된다.
        check_times 변경은 Pod 재시작 후에 새 cron 으로 등록된다.
      </p>
      {error && <p className="error">{error}</p>}
      {policy === null ? (
        <p>loading…</p>
      ) : (
        <form className="table-form" onSubmit={onSave}>
          <div className="grid">
            <label className="span-2">
              Check times (KST, comma-separated HH:MM)
              <input
                value={checkTimes}
                onChange={(e) => setCheckTimes(e.target.value)}
                placeholder="06:00, 07:00, 08:00, 08:20, 08:40, 09:00"
              />
            </label>
            <label>
              Report time (KST)
              <input
                type="time"
                value={reportTime}
                onChange={(e) => setReportTime(e.target.value)}
              />
            </label>
            <label>
              Default Δ% threshold
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={defaultThreshold}
                onChange={(e) => setDefaultThreshold(e.target.value)}
              />
            </label>
            <label>
              Retention days
              <input
                type="number"
                min={1}
                max={3650}
                value={retentionDays}
                onChange={(e) => setRetentionDays(e.target.value)}
              />
            </label>
            <label>
              condition_query max bytes
              <input
                type="number"
                min={1024}
                value={conditionMaxBytes}
                onChange={(e) => setConditionMaxBytes(e.target.value)}
              />
            </label>
            <label>
              Dedup strategy
              <select
                value={dedupStrategy}
                onChange={(e) => setDedupStrategy(e.target.value)}
              >
                <option value="every-hour-resend">every-hour-resend</option>
                <option value="state-change-only">state-change-only</option>
              </select>
            </label>
          </div>
          <button type="submit" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
          {savedNote && <p className="run-meta">{savedNote}</p>}
        </form>
      )}
    </section>
  )
}
