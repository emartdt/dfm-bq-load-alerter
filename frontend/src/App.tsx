import { useEffect, useState } from 'react'

type HealthStatus = 'unknown' | 'ok' | 'error'

interface Alert {
  id: string
  severity: string
  message: string
  occurred_at: string
}

interface VersionResponse {
  version: string
}

function App() {
  const [health, setHealth] = useState<HealthStatus>('unknown')
  const [version, setVersion] = useState<string>('')
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [error, setError] = useState<string>('')

  useEffect(() => {
    fetch('/healthz')
      .then((res) => (res.ok ? setHealth('ok') : setHealth('error')))
      .catch(() => setHealth('error'))

    fetch('/api/version')
      .then((res) => res.json() as Promise<VersionResponse>)
      .then((data) => setVersion(data.version))
      .catch(() => setVersion('?'))

    fetch('/api/alerts')
      .then((res) => res.json() as Promise<Alert[]>)
      .then(setAlerts)
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <main>
      <header>
        <h1>DFM BigQuery Load Alerter</h1>
        <p className="meta">
          backend: <span className={`badge badge-${health}`}>{health}</span>
          {version && <span> · v{version}</span>}
        </p>
      </header>

      <section>
        <h2>Alerts</h2>
        {error && <p className="error">{error}</p>}
        {alerts.length === 0 && !error && <p>No alerts.</p>}
        <ul>
          {alerts.map((alert) => (
            <li key={alert.id}>
              <span className={`severity severity-${alert.severity}`}>{alert.severity}</span>
              <span className="message">{alert.message}</span>
              <span className="occurred">{alert.occurred_at}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  )
}

export default App
