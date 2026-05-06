import { Link, Route, Routes } from 'react-router-dom'

import { TokenInput } from './components/TokenInput'
import { Home } from './pages/Home'
import { Tables } from './pages/Tables'

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
        </nav>
        <TokenInput />
      </header>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/tables" element={<Tables />} />
      </Routes>
    </main>
  )
}

export default App
