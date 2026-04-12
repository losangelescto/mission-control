/**
 * Next.js App Router passes `searchParams` values as `string | string[] | undefined`.
 * Coercing with `Number(params.selected)` is unsafe: e.g. `Number(["1","2"])` is `NaN`
 * (comma-joined string), and duplicate query keys can surface as a string array.
 */
export function firstSearchParam(
  value: string | string[] | undefined
): string | undefined {
  if (value === undefined) return undefined;
  const s = Array.isArray(value) ? value[0] : value;
  return s === undefined || s === "" ? undefined : s;
}

/** Parse a positive integer route/query param, or undefined if missing/invalid. */
export function parsePositiveIntParam(
  value: string | string[] | undefined
): number | undefined {
  const raw = firstSearchParam(value)?.trim();
  if (!raw) return undefined;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return undefined;
  return n;
}
