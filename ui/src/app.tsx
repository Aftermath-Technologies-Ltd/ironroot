// Author: Bradley R. Kinnard
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'
import { Beliefs } from './pages/beliefs'
import { Dashboard } from './pages/dashboard'
import { RunDetail } from './pages/run_detail'
import { Runs } from './pages/runs'
import { Strategies } from './pages/strategies'

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const location = useLocation()
  const isActive = location.pathname === to || (to !== '/' && location.pathname.startsWith(to))
  return (
    <Link
      to={to}
      style={{
        color: isActive ? 'var(--primary)' : 'inherit',
        fontWeight: isActive ? 'bold' : 'normal',
        borderBottom: isActive ? '2px solid var(--primary)' : '2px solid transparent',
        paddingBottom: '0.25rem',
      }}
    >
      {children}
    </Link>
  )
}

function Navigation() {
  return (
    <nav className="nav">
      <NavLink to="/">Dashboard</NavLink>
      <NavLink to="/runs">Runs</NavLink>
      <NavLink to="/beliefs">Beliefs</NavLink>
      <NavLink to="/strategies">Strategies</NavLink>
    </nav>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Navigation />
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/beliefs" element={<Beliefs />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
