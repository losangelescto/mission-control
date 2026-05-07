/**
 * Centralized feature flags for the v2 design migration.
 *
 * Each flag keeps a piece of UI alive in code so it can be re-enabled
 * via env var without touching JSX. Flags read NEXT_PUBLIC_* so they're
 * inlined at build time and work identically on the server and client.
 *
 * Convention: flags default to OFF (= the v2 'Calm' behavior). Set the
 * env var to "true" to opt in to the legacy / experimental UI.
 */

function flag(envValue: string | undefined): boolean {
  return envValue === "true";
}

export const flags = {
  /**
   * When true, the Tasks route shows the inline "Suggested Tasks —
   * Extracted from Sources" panel at the bottom of the page. v2 moves
   * this surface to the dedicated /tasks/candidates page; we keep the
   * inline duplicate behind a flag for operators who relied on seeing
   * candidates next to their open task list. Default off — the canonical
   * location is now /tasks/candidates.
   */
  inlineCandidatesOnTasks: flag(process.env.NEXT_PUBLIC_ENABLE_INLINE_CANDIDATES),
} as const;
