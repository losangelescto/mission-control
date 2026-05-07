// Pure formatters extracted from the TimeDisplay component so they can be
// unit-tested under vitest's node environment (no DOM). The component
// renders the SSR variant on first paint and the local variant after mount.

export type TimeFormat = "datetime" | "date";

const FORMATS: Record<TimeFormat, Intl.DateTimeFormatOptions> = {
  datetime: {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  },
  date: {
    month: "short",
    day: "numeric",
    year: "numeric",
  },
};

export function formatIsoForSsr(iso: string, format: TimeFormat = "datetime"): string {
  return new Date(iso).toLocaleString("en-US", { ...FORMATS[format], timeZone: "UTC" });
}

export function formatIsoForLocal(iso: string, format: TimeFormat = "datetime"): string {
  return new Date(iso).toLocaleString("en-US", FORMATS[format]);
}

/**
 * Editorial due-date formatter for v2 task cards. Returns an absolute date
 * string ("May 12") plus an `overdue` flag, computed server-side.
 *
 * Timezone caveat: this runs in the server's TZ (typically UTC). Tasks due
 * "today" in the user's local TZ may format as "yesterday" or "tomorrow"
 * depending on time-of-day. Acceptable for editorial copy; any client that
 * needs perfect calendar-day semantics should re-format on mount.
 *
 * @param now Optional override for tests. Defaults to the current time.
 */
export function formatTaskDue(
  iso: string | null,
  now: Date = new Date()
): { text: string; overdue: boolean } {
  if (!iso) return { text: "—", overdue: false };
  const due = new Date(iso);
  const overdue = due.getTime() < now.getTime();
  const text = due.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return { text, overdue };
}
