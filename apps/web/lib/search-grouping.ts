import type { SearchResult, SearchResultType } from "@/lib/api/types";

export type GroupKey = "tasks" | "sources" | "reviews" | "canon";

export type Group = {
  key: GroupKey;
  label: string;
  items: SearchResult[];
};

export const TYPE_LABEL: Record<SearchResultType, string> = {
  task: "Task",
  task_update: "Update",
  sub_task: "Sub-task",
  obstacle: "Obstacle",
  source: "Source",
  source_chunk: "Source",
  review: "Review",
  canon: "Canon",
};

export const TYPE_ICON: Record<SearchResultType, string> = {
  task: "▣",
  task_update: "▤",
  sub_task: "▢",
  obstacle: "▲",
  source: "▦",
  source_chunk: "▦",
  review: "✎",
  canon: "★",
};

const GROUP_DEFS: { key: GroupKey; label: string; types: readonly SearchResultType[] }[] = [
  { key: "tasks",   label: "Tasks",   types: ["task", "task_update", "sub_task", "obstacle"] },
  { key: "sources", label: "Sources", types: ["source", "source_chunk"] },
  { key: "reviews", label: "Reviews", types: ["review"] },
  { key: "canon",   label: "Canon",   types: ["canon"] },
];

/**
 * Bucket a flat list of search results by user-facing group, preserving
 * the relative order within each group. Empty groups are dropped so the
 * caller can iterate the return value directly.
 *
 * Result types not in any GROUP_DEFS bucket are ignored — this is
 * defensive against the backend adding new types before the frontend
 * type union is updated.
 */
export function groupSearchResults(results: SearchResult[] | undefined | null): Group[] {
  if (!results || results.length === 0) return [];
  const groups: Group[] = [];
  for (const def of GROUP_DEFS) {
    const items = results.filter((r) => def.types.includes(r.type));
    if (items.length > 0) groups.push({ key: def.key, label: def.label, items });
  }
  return groups;
}
