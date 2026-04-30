import type { SubTaskDraft } from "@/lib/api/types";

/**
 * Filter a drafts list down to only those the user has not deselected.
 * Pure helper — extracted so it can be unit-tested without React.
 */
export function pickSelectedDrafts(
  drafts: SubTaskDraft[],
  deselectedIndexes: ReadonlySet<number>,
): SubTaskDraft[] {
  return drafts.filter((_, i) => !deselectedIndexes.has(i));
}

/**
 * Toggle membership of an index in a Set in an immutable-ish way.
 */
export function toggleIndex(
  set: ReadonlySet<number>,
  index: number,
): Set<number> {
  const next = new Set(set);
  if (next.has(index)) next.delete(index);
  else next.add(index);
  return next;
}
