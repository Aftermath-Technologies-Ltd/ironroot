// Author: Bradley R. Kinnard
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { Beliefs } from './pages/beliefs'
import { Dashboard } from './pages/dashboard'
import { RunDetail } from './pages/run_detail'
import { Strategies } from './pages/strategies'
import { Tests } from './pages/tests'

export function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="nav">
          <Link to="/">Dashboard</Link>
          <Link to="/strategies">Strategies</Link>
          <Link to="/beliefs">Beliefs</Link>
          <Link to="/tests">Tests</Link>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/beliefs" element={<Beliefs />} />
            <Route path="/tests" element={<Tests />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
