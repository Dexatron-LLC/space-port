/**
 * App shell: the navy header (orbit mark + product name), the two-tab navigation and the
 * current screen. There is no router; a single piece of state picks the screen.
 */
import { useState } from 'react'
import CharterScreen from './CharterScreen'
import FleetScreen from './FleetScreen'

type Tab = 'charter' | 'fleet'

const TABS: { id: Tab; label: string }[] = [
  { id: 'charter', label: 'Charter a Ship' },
  { id: 'fleet', label: 'Fleet Dashboard' },
]

/** The root component: header, tab bar and whichever screen the selected tab shows. */
export default function App() {
  const [tab, setTab] = useState<Tab>('charter')

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="brand">
            <svg className="mark" viewBox="0 0 26 26" aria-hidden="true">
              <circle cx="13" cy="13" r="5" />
              <ellipse cx="13" cy="13" rx="11.5" ry="4.5" transform="rotate(-25 13 13)" />
              <circle className="dot" cx="23.4" cy="8.1" r="1.6" />
            </svg>
            <span>Spaceport Charter System</span>
          </div>
          <nav className="tabs" aria-label="Main">
            {TABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                className="tab"
                aria-current={tab === id ? 'page' : undefined}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="page">
        {/* Only the current screen is mounted, so the dashboard re-fetches on every visit. */}
        {tab === 'charter' ? <CharterScreen /> : <FleetScreen />}
      </main>
    </div>
  )
}
