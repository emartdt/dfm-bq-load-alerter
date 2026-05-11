import { Link, NavLink } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

const NAV_ITEMS: Array<{ to: string; label: string; end?: boolean }> = [
  { to: '/', label: '홈', end: true },
  { to: '/tables', label: '테이블' },
  { to: '/recipients', label: '수신자' },
  { to: '/webhooks', label: '웹훅' },
  { to: '/history', label: '이력' },
  { to: '/policy', label: '정책' },
]

export function Header() {
  const { user, logout } = useAuth()
  return (
    <>
      <header className="global-nav">
        <Link to="/" className="nav-brand">
          DFM BigQuery Load Alerter
        </Link>
        <span className="nav-spacer" />
        {user?.email && <span className="nav-user">{user.email}</span>}
        <button type="button" className="utility" onClick={logout}>
          로그아웃
        </button>
      </header>
      <nav className="sub-nav" aria-label="주 메뉴">
        <Link to="/" className="sub-nav-title">
          BQ 적재 알리미
        </Link>
        <div className="sub-nav-links">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? 'sub-nav-link active' : 'sub-nav-link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </>
  )
}
