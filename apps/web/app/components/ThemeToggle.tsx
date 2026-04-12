'use client'

import { useEffect, useState } from 'react'

type ThemeStorageValue = 'dark' | 'light'

export function isDarkClassPresent(documentElement: {
  classList: { contains: (token: string) => boolean }
}) {
  return documentElement.classList.contains('dark')
}

export function getThemeStorageValue(isDark: boolean): ThemeStorageValue {
  return isDark ? 'dark' : 'light'
}

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    // Avoid calling setState synchronously inside an effect body (eslint rule).
    const rafId = window.requestAnimationFrame(() => {
      setMounted(true)
      setIsDark(isDarkClassPresent(document.documentElement))
    })
    return () => window.cancelAnimationFrame(rafId)
  }, [])

  function toggle() {
    const next = !isDark
    document.documentElement.classList.toggle('dark', next)
    try { localStorage.setItem('mc-theme', getThemeStorageValue(next)) } catch { /* noop */ }
    setIsDark(next)
  }

  if (!mounted) {
    return <div style={{ width: '32px', height: '32px', flexShrink: 0 }} />
  }

  return (
    <button
      className="theme-toggle"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}
