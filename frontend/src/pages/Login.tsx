import { useAuth } from '../auth/AuthContext'

export function Login() {
  const { login } = useAuth()
  return (
    <main style={{ maxWidth: 480, margin: '4rem auto', textAlign: 'center' }}>
      <h1>DFM BigQuery Load Alerter</h1>
      <p>계속하려면 회사 계정으로 로그인하세요.</p>
      <button type="button" onClick={login} style={{ padding: '0.75rem 1.5rem', fontSize: '1rem' }}>
        로그인하기
      </button>
    </main>
  )
}
