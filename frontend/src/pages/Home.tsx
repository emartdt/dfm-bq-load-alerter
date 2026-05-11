import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

type HealthStatus = 'unknown' | 'ok' | 'error'

interface VersionResponse {
  version: string
}

const HEALTH_LABEL: Record<HealthStatus, string> = {
  unknown: '확인 중',
  ok: '정상',
  error: '오류',
}

export function Home() {
  const [health, setHealth] = useState<HealthStatus>('unknown')
  const [version, setVersion] = useState<string>('')

  useEffect(() => {
    fetch('/healthz')
      .then((res) => (res.ok ? setHealth('ok') : setHealth('error')))
      .catch(() => setHealth('error'))

    fetch('/api/version')
      .then((res) => res.json() as Promise<VersionResponse>)
      .then((data) => setVersion(data.version))
      .catch(() => setVersion('?'))
  }, [])

  return (
    <section>
      <header className="page-header">
        <h1 className="page-title">대시보드</h1>
        <p className="page-subtitle">BigQuery 적재 모니터링과 알림 정책을 한 곳에서.</p>
      </header>

      <div className="card">
        <h2 className="card-title">시스템 상태</h2>
        <p className="meta">
          백엔드 <span className={`badge badge-${health}`}>{HEALTH_LABEL[health]}</span>
          {version && <span> · v{version}</span>}
        </p>
        <p style={{ marginTop: 16 }}>
          <Link to="/tables" className="btn btn-primary btn-small">
            테이블 관리로 이동
          </Link>
        </p>
      </div>
    </section>
  )
}
