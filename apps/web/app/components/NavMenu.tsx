'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import CanonChangesBadge from './CanonChangesBadge'
import SuggestedTasksBadge from './SuggestedTasksBadge'

const NAV_LINKS = [
  { href: '/dashboard',        label: 'Dashboard'      },
  { href: '/tasks',            label: 'Tasks'          },
  { href: '/tasks/candidates', label: 'Suggested'      },
  { href: '/sources',          label: 'Sources'        },
  { href: '/canon-changes',    label: 'Canon Changes'  },
  { href: '/review',           label: 'Review'         },
  { href: '/metrics',          label: 'Metrics'        },
]

function MenuIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="3" y1="6"  x2="21" y2="6"  />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="18" y1="6"  x2="6"  y2="18" />
      <line x1="6"  y1="6"  x2="18" y2="18" />
    </svg>
  )
}

export function NavMenu() {
  const [open, setOpen] = useState(false)
  const pathname = usePathname()

  // Close drawer on navigation
  useEffect(() => {
    // Avoid calling setState synchronously inside an effect body (eslint rule).
    const rafId = window.requestAnimationFrame(() => setOpen(false))
    return () => window.cancelAnimationFrame(rafId)
  }, [pathname])

  // Close drawer on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Prevent body scroll when drawer is open
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  return (
    <>
      {/* ── Desktop nav ───────────────────────────── */}
      <nav className="nav-desktop" aria-label="Main navigation">
        {NAV_LINKS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`nav-link${pathname === href ? ' nav-link-active' : ''}`}
          >
            {label}
            {href === '/canon-changes' ? <CanonChangesBadge /> : null}
            {href === '/tasks/candidates' ? <SuggestedTasksBadge /> : null}
          </Link>
        ))}
      </nav>

      {/* ── Mobile hamburger ──────────────────────── */}
      <button
        className="nav-hamburger"
        onClick={() => setOpen(v => !v)}
        aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={open}
      >
        {open ? <CloseIcon /> : <MenuIcon />}
      </button>

      {/* ── Mobile drawer ─────────────────────────── */}
      {open && (
        <>
          <div
            className="nav-overlay"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <nav className="nav-drawer" aria-label="Mobile navigation">
            {NAV_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`nav-drawer-link${pathname === href ? ' nav-drawer-link-active' : ''}`}
                onClick={() => setOpen(false)}
              >
                {label}
              </Link>
            ))}
          </nav>
        </>
      )}
    </>
  )
}
