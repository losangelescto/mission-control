// Pure functions for the Dashboard kanban board state. Extracted so they
// can be unit-tested under vitest's node environment without DOM, dnd
// library mocks, or React.

import type { Task, TaskStatus } from "./api/types";

export type KanbanColumns = Record<TaskStatus, Task[]>;

export const KANBAN_STATUSES: ReadonlyArray<TaskStatus> = [
  "up_next",
  "in_progress",
  "blocked",
  "completed",
  "backlog",
] as const;

export function emptyKanbanColumns(): KanbanColumns {
  return {
    up_next: [],
    in_progress: [],
    blocked: [],
    completed: [],
    backlog: [],
  };
}

export function groupTasksByStatus(tasks: Task[]): KanbanColumns {
  const grouped = emptyKanbanColumns();
  for (const task of tasks) {
    if (grouped[task.status]) grouped[task.status].push(task);
  }
  return grouped;
}

/**
 * Optimistic move applied on drop. Same column → reorder. Cross column →
 * remove from source, splice into destination, update task.status to the
 * new column. Returns a new state object; never mutates the input.
 *
 * No-op cases:
 *   - destination missing (drop outside any droppable)
 *   - same column AND same index (drop on self)
 *   - source index points past the end of the source column
 */
export function moveTask(
  state: KanbanColumns,
  source: { droppableId: string; index: number },
  destination: { droppableId: string; index: number } | null,
): KanbanColumns {
  if (!destination) return state;
  if (
    source.droppableId === destination.droppableId &&
    source.index === destination.index
  ) {
    return state;
  }

  const srcKey = source.droppableId as TaskStatus;
  const dstKey = destination.droppableId as TaskStatus;

  if (!state[srcKey] || !state[dstKey]) return state;

  const srcList = [...state[srcKey]];
  const moved = srcList[source.index];
  if (!moved) return state;
  srcList.splice(source.index, 1);

  const updated: Task = { ...moved, status: dstKey };
  const next: KanbanColumns = { ...state };

  if (srcKey === dstKey) {
    srcList.splice(destination.index, 0, updated);
    next[srcKey] = srcList;
  } else {
    next[srcKey] = srcList;
    const dstList = [...state[dstKey]];
    dstList.splice(destination.index, 0, updated);
    next[dstKey] = dstList;
  }
  return next;
}

/**
 * Updates a single task in-place across whichever column it's currently in.
 * Used after a dialog (Block / Unblock) returns a new authoritative task
 * from the API — moves the card from its current column to whatever the
 * server says its new status is, replacing the old task object entirely.
 */
export function applyServerTaskUpdate(
  state: KanbanColumns,
  updatedTask: Task,
): KanbanColumns {
  const next = { ...state };
  let removed = false;
  for (const status of KANBAN_STATUSES) {
    const idx = (next[status] ?? []).findIndex(t => t.id === updatedTask.id);
    if (idx !== -1) {
      next[status] = [...next[status]];
      next[status].splice(idx, 1);
      removed = true;
      break;
    }
  }
  // Always insert at the front of the destination column — newer activity
  // surfaces on top, the server's ordering can stabilise on next refetch.
  if (removed || true) {
    next[updatedTask.status] = [updatedTask, ...(next[updatedTask.status] ?? [])];
  }
  return next;
}
