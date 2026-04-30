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
