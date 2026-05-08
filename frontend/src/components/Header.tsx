import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function Header() {
  const { user, logout } = useAuth()
  return (
    <header>
      <h1>
        <Link to="/">DFM BigQuery Load Alerter</Link>
      </h1>
      <nav>
        <Link to="/">Home</Link>
        {' · '}
        <Link to="/tables">Tables</Link>
        {' · '}
        <Link to="/groups">Groups</Link>
        {' · '}
        <Link to="/recipients">Recipients</Link>
        {' · '}
        <Link to="/webhooks">Webhooks</Link>
        {' · '}
        <Link to="/history">History</Link>
        {' · '}
        <Link to="/policy">Policy</Link>
      </nav>
      <div style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>
        {user?.email && <span style={{ marginRight: '1rem' }}>{user.email}</span>}
        <button type="button" onClick={logout}>로그아웃</button>
      </div>
    </header>
  )
}
