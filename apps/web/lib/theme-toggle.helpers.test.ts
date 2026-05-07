import { describe, expect, it } from 'vitest'

import {
  THEME_STORAGE_KEY,
  getThemeStorageValue,
  isDarkThemeAttr,
} from '../app/components/ThemeToggle'

describe('ThemeToggle helpers', () => {
  it('detects dark from data-theme="dark" on a documentElement-like object', () => {
    const documentElementLike = {
      getAttribute: (name: string) => (name === 'data-theme' ? 'dark' : null),
    }

    expect(isDarkThemeAttr(documentElementLike)).toBe(true)
  })

  it('returns light storage value when isDark is false', () => {
    expect(getThemeStorageValue(false)).toBe('light')
  })

  it('uses mc.theme as the localStorage key', () => {
    expect(THEME_STORAGE_KEY).toBe('mc.theme')
  })
})
