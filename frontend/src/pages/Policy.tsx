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
  const [dedupStrategy, setDedupStrategy] = useState<string>('every-hour-resend')
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
      setDedupStrategy(p.dedup_strategy)
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
        dedup_strategy: dedupStrategy,
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
          시스템 전역 정책 (singleton). 변경은 다음 cron부터 적용되며, 점검 시간 변경은 Pod 재시작 후 새 cron으로 등록됩니다.
        </p>
      </header>

      {error && <p className="error">{error}</p>}

      {policy === null ? (
        <p className="loading">불러오는 중…</p>
      ) : (
        <form className="card" onSubmit={onSave}>
          <h2 className="card-title">전역 정책</h2>
          <div className="form-grid">
            <label className="field span-2">
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
                중복 전송 전략{' '}
                <span className="info-tip" tabIndex={0}>
                  <span className="info-icon" aria-hidden="true">ⓘ</span>
                  <span className="info-tip-body" role="tooltip">
                    <strong>FAIL 알림 재전송 방식</strong>
                    <ul>
                      <li>
                        <code>매 시간 재전송</code> — 직전 점검과 상태가 같아도 FAIL이면 매 점검마다 다시 전송합니다. 누락은 줄지만 알림 수가 많아집니다.
                      </li>
                      <li>
                        <code>상태 변경 시만</code> — 직전 점검 대비 상태(성공↔실패)가 바뀌었을 때만 전송하도록 의도된 옵션입니다. 노이즈는 줄지만 지속 실패에 대한 환기가 줄어듭니다.
                      </li>
                    </ul>
                    <em>* 현재 버전에서는 두 옵션이 동일하게 동작합니다 (백엔드에 분기 미구현).</em>
                  </span>
                </span>
              </span>
              <select
                value={dedupStrategy}
                onChange={(e) => setDedupStrategy(e.target.value)}
              >
                <option value="every-hour-resend">매 시간 재전송</option>
                <option value="state-change-only">상태 변경 시만</option>
              </select>
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
