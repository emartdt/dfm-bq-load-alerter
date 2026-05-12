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
  const [defaultBuffer, setDefaultBuffer] = useState<string>('30')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const p = await getPolicy()
      setPolicy(p)
      setCheckTimes(p.check_times.join(', '))
      setReportTime(p.report_time.slice(0, 5))
      setDefaultThreshold(String(p.default_threshold_percent))
      setRetentionDays(String(p.retention_days))
      setDefaultBuffer(String(p.default_buffer_minutes))
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
        default_buffer_minutes: Number(defaultBuffer),
      })
      setPolicy(updated)
      setSavedNote(`${new Date(updated.updated_at).toLocaleString()}에 저장됨`)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <header className="page-header">
        <h1 className="page-title">알림 정책</h1>
        <p className="page-subtitle">
          시스템 전역 정책 (singleton). 점검 시각·리포트 시각 변경은 약 30초 이내에 스케줄러에 자동 반영됩니다.
        </p>
      </header>

      {error && <p className="error">{error}</p>}

      {policy === null ? (
        <p className="loading">불러오는 중…</p>
      ) : (
        <form className="card" onSubmit={onSave}>
          <h2 className="card-title">전역 정책</h2>
          <div className="form-grid">
            <label className="field span-all">
              <span>
                점검 시각 <span className="field-hint">KST, HH:MM 콤마 구분</span>
              </span>
              <input
                value={checkTimes}
                onChange={(e) => setCheckTimes(e.target.value)}
                placeholder="06:00, 07:00, 08:00, 08:20, 08:40, 09:00"
              />
            </label>
            <label className="field">
              <span>리포트 시각 (KST)</span>
              <input
                type="time"
                value={reportTime}
                onChange={(e) => setReportTime(e.target.value)}
              />
            </label>
            <label className="field">
              <span>
                기본 증감률 임계치 <span className="field-hint">%</span>
              </span>
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                value={defaultThreshold}
                onChange={(e) => setDefaultThreshold(e.target.value)}
              />
            </label>
            <label className="field">
              <span>이력 보관 일수</span>
              <input
                type="number"
                min={1}
                max={3650}
                value={retentionDays}
                onChange={(e) => setRetentionDays(e.target.value)}
              />
            </label>
            <label className="field">
              <span>
                기본 버퍼 <span className="field-hint">분</span>
              </span>
              <input
                type="number"
                min={1}
                max={1440}
                value={defaultBuffer}
                onChange={(e) => setDefaultBuffer(e.target.value)}
              />
            </label>
          </div>
          <div className="actions">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? '저장 중…' : '저장'}
            </button>
            {savedNote && <span className="run-meta">{savedNote}</span>}
          </div>
        </form>
      )}
    </section>
  )
}
