import { Link, Route, Routes } from 'react-router-dom'

import { TokenInput } from './components/TokenInput'
import { Home } from './pages/Home'
import { Recipients } from './pages/Recipients'
import { Tables } from './pages/Tables'
import { Webhooks } from './pages/Webhooks'

function App() {
  return (
    <main>
      <header>
        <h1>
          <Link to="/">DFM BigQuery Load Alerter</Link>
        </h1>
        <nav>
          <Link to="/">Home</Link>
          {' · '}
          <Link to="/tables">Tables</Link>
          {' · '}
          <Link to="/recipients">Recipients</Link>
          {' · '}
          <Link to="/webhooks">Webhooks</Link>
        </nav>
        <TokenInput />
      </header>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/tables" element={<Tables />} />
        <Route path="/recipients" element={<Recipients />} />
        <Route path="/webhooks" element={<Webhooks />} />
      </Routes>
    </main>
  )
}

export default App
