import { describe, expect, it } from 'vitest'

import {
  getThemeStorageValue,
  isDarkClassPresent,
} from '../app/components/ThemeToggle'

describe('ThemeToggle helpers', () => {
  it('detects dark class from a documentElement-like object', () => {
    const documentElementLike = {
      classList: {
        contains: (token: string) => token === 'dark',
      },
    }

    expect(isDarkClassPresent(documentElementLike)).toBe(true)
  })

  it('returns light storage value when isDark is false', () => {
    expect(getThemeStorageValue(false)).toBe('light')
  })
})

