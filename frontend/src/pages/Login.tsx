import { useAuth } from '../auth/AuthContext'

export function Login() {
  const { login } = useAuth()
  return (
    <main className="login">
      <div className="login-card">
        <h1 className="login-title">DFM BigQuery 적재 알리미</h1>
        <p className="login-lead">계속하려면 회사 계정으로 로그인하세요.</p>
        <button type="button" onClick={login} className="btn btn-primary btn-large">
          로그인
        </button>
      </div>
    </main>
  )
}
