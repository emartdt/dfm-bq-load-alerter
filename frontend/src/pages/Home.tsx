import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

type HealthStatus = 'unknown' | 'ok' | 'error'

interface VersionResponse {
  version: string
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
      <h2>Status</h2>
      <p className="meta">
        backend: <span className={`badge badge-${health}`}>{health}</span>
        {version && <span> · v{version}</span>}
      </p>
      <p>
        <Link to="/tables">Tables &rarr;</Link>
      </p>
    </section>
  )
}
