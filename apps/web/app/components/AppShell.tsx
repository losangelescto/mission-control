'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

import CanonChangesBadge from './CanonChangesBadge'
import SearchBar from './SearchBar'
import SuggestedTasksBadge from './SuggestedTasksBadge'
import { ThemeToggle } from './ThemeToggle'

type BadgeKind = 'canon' | 'suggested'

const NAV_LINKS: Array<{ href: string; label: string; badge?: BadgeKind }> = [
  { href: '/dashboard',        label: 'Dashboard'                          },
  { href: '/tasks',            label: 'Tasks'                              },
  { href: '/tasks/candidates', label: 'Suggested',     badge: 'suggested'  },
  { href: '/sources',          label: 'Sources'                            },
  { href: '/canon-changes',    label: 'Canon Changes', badge: 'canon'      },
  { href: '/review',           label: 'Review'                             },
  { href: '/metrics',          label: 'Metrics'                            },
]

function HamburgerIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M2 5h14M2 9h14M2 13h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

// Render after mount to avoid SSR/CSR timezone mismatches.
function HeaderDate() {
  const [text, setText] = useState('')
  useEffect(() => {
    const id = window.requestAnimationFrame(() => {
      const d = new Date()
      setText(d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }))
    })
    return () => window.cancelAnimationFrame(id)
  }, [])
  if (!text) return null
  return (
    <span
      className="serif header-date"
      style={{ fontStyle: 'italic', fontSize: 13, color: 'var(--ink-soft)' }}
    >
      {text}
    </span>
  )
}

function SidebarBody({
  pathname,
  onNavigate,
}: {
  pathname: string
  onNavigate?: () => void
}) {
  return (
    <>
      <div style={{ padding: '0 24px 22px', borderBottom: '1px solid var(--line)' }}>
        <Link
          href="/"
          onClick={onNavigate}
          className="serif"
          style={{
            display: 'block',
            fontSize: 22,
            fontWeight: 500,
            letterSpacing: '-0.005em',
            color: 'var(--ink)',
            textDecoration: 'none',
          }}
        >
          Mission Control
        </Link>
        <div
          className="serif"
          style={{
            fontSize: 12,
            fontStyle: 'italic',
            color: 'var(--ink-faint)',
            marginTop: 4,
            letterSpacing: '0.01em',
          }}
        >
          Operations
        </div>
      </div>

      <nav
        aria-label="Main navigation"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          padding: '14px 12px',
          gap: 1,
          overflowY: 'auto',
        }}
      >
        {NAV_LINKS.map(item => {
          const active = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={`shell-nav-link${active ? ' shell-nav-link-active' : ''}`}
            >
              <span>{item.label}</span>
              {item.badge === 'canon' ? <CanonChangesBadge /> : null}
              {item.badge === 'suggested' ? <SuggestedTasksBadge /> : null}
            </Link>
          )
        })}
      </nav>

      <div
        style={{
          padding: 12,
          borderTop: '1px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
        }}
      >
        <ThemeToggle />
      </div>
    </>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Close drawer on route change. requestAnimationFrame avoids the
  // react-hooks/set-state-in-effect lint rule.
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setDrawerOpen(false))
    return () => window.cancelAnimationFrame(id)
  }, [pathname])

  // Close drawer on Escape.
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') setDrawerOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Lock body scroll while the drawer is open.
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [drawerOpen])

  return (
    <div className="shell">
      <aside className="sidebar-desktop">
        <SidebarBody pathname={pathname} />
      </aside>

      {drawerOpen ? (
        <>
          <div
            className="drawer-backdrop"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <aside className="drawer-panel" aria-label="Mobile navigation">
            <SidebarBody
              pathname={pathname}
              onNavigate={() => setDrawerOpen(false)}
            />
          </aside>
        </>
      ) : null}

      <div className="shell-main">
        <header className="topbar-mobile" aria-label="Mobile header">
          <button
            type="button"
            className="hamburger-btn"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation menu"
          >
            <HamburgerIcon />
          </button>
          <span className="serif" style={{ fontSize: 16, fontWeight: 500, flex: 1 }}>
            Mission Control
          </span>
          <ThemeToggle />
        </header>

        <header className="header-pad">
          <div className="search-shell" style={{ flex: 1, maxWidth: 480, position: 'relative' }}>
            <SearchBar />
          </div>
          <span style={{ flex: 1 }} />
          <div
            className="header-meta-extra"
            style={{ display: 'flex', alignItems: 'center', gap: 14 }}
          >
            <HeaderDate />
          </div>
        </header>

        <div className="main-content-pad">{children}</div>
      </div>
    </div>
  )
}
