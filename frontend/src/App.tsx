import { Outlet, Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { Header } from './components/Header'
import { History } from './pages/History'
import { Home } from './pages/Home'
import { Login } from './pages/Login'
import { PolicyPage } from './pages/Policy'
import { Recipients } from './pages/Recipients'
import { Tables } from './pages/Tables'
import { Webhooks } from './pages/Webhooks'

function Layout() {
  return (
    <main>
      <Header />
      <Outlet />
    </main>
  )
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/tables" element={<Tables />} />
            <Route path="/recipients" element={<Recipients />} />
            <Route path="/webhooks" element={<Webhooks />} />
            <Route path="/history" element={<History />} />
            <Route path="/policy" element={<PolicyPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
