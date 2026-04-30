// Pure helper for the SearchBar empty-state hint: when a user types a
// hyphenated/period-separated/underscored phrase like "vendor-policy" the
// FTS analyzer treats those characters as separators, so an exact-phrase
// query frequently returns no rows. We surface a one-line nudge so the
// user knows to retry with individual words. Extracted as a pure helper
// so it can be vitest-tested without rendering React.

const SEPARATOR_PATTERN = /[-_./]/;

export function shouldShowHyphenHint(query: string, hasResults: boolean): boolean {
  if (hasResults) return false;
  return SEPARATOR_PATTERN.test(query);
}

export const HYPHEN_HINT_TEXT =
  "No matches. Try searching for individual words — hyphens and special characters are treated as separators.";
