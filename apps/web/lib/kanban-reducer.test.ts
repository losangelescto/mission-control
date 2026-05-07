import { describe, expect, it } from "vitest";

import type { Task, TaskStatus } from "./api/types";
import {
  applyServerTaskUpdate,
  emptyKanbanColumns,
  groupTasksByStatus,
  moveTask,
} from "./kanban-reducer";

function makeTask(id: number, status: TaskStatus, title = `Task ${id}`): Task {
  return {
    id,
    title,
    description: "",
    objective: "",
    standard: "",
    status,
    priority: "medium",
    owner_name: "Anyone",
    assigner_name: "self",
    due_at: null,
    source_confidence: null,
    canon_update_pending: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("groupTasksByStatus", () => {
  it("buckets tasks by status, leaves other columns empty", () => {
    const tasks = [
      makeTask(1, "up_next"),
      makeTask(2, "blocked"),
      makeTask(3, "up_next"),
    ];
    const grouped = groupTasksByStatus(tasks);
    expect(grouped.up_next).toHaveLength(2);
    expect(grouped.blocked).toHaveLength(1);
    expect(grouped.in_progress).toHaveLength(0);
    expect(grouped.completed).toHaveLength(0);
    expect(grouped.backlog).toHaveLength(0);
  });

  it("preserves task object references", () => {
    const t = makeTask(42, "in_progress");
    const grouped = groupTasksByStatus([t]);
    expect(grouped.in_progress[0]).toBe(t);
  });
});

describe("moveTask", () => {
  function seed(): ReturnType<typeof emptyKanbanColumns> {
    const cols = emptyKanbanColumns();
    cols.up_next = [makeTask(1, "up_next"), makeTask(2, "up_next")];
    cols.in_progress = [makeTask(3, "in_progress")];
    cols.blocked = [];
    return cols;
  }

  it("returns the same state when destination is null (drop outside)", () => {
    const state = seed();
    const next = moveTask(state, { droppableId: "up_next", index: 0 }, null);
    expect(next).toBe(state);
  });

  it("returns the same state when source and destination are identical", () => {
    const state = seed();
    const next = moveTask(
      state,
      { droppableId: "up_next", index: 0 },
      { droppableId: "up_next", index: 0 },
    );
    expect(next).toBe(state);
  });

  it("reorders within the same column without mutating input", () => {
    const state = seed();
    const next = moveTask(
      state,
      { droppableId: "up_next", index: 0 },
      { droppableId: "up_next", index: 1 },
    );
    expect(next).not.toBe(state);
    expect(state.up_next.map(t => t.id)).toEqual([1, 2]);
    expect(next.up_next.map(t => t.id)).toEqual([2, 1]);
  });

  it("moves a task across columns and updates its status", () => {
    const state = seed();
    const next = moveTask(
      state,
      { droppableId: "up_next", index: 0 },
      { droppableId: "in_progress", index: 0 },
    );
    expect(next.up_next.map(t => t.id)).toEqual([2]);
    expect(next.in_progress.map(t => t.id)).toEqual([1, 3]);
    expect(next.in_progress[0].status).toBe("in_progress");
    // Source state untouched
    expect(state.up_next.map(t => t.id)).toEqual([1, 2]);
    expect(state.in_progress[0].status).toBe("in_progress");
  });

  it("returns input unchanged when source index points past the end", () => {
    const state = seed();
    const next = moveTask(
      state,
      { droppableId: "blocked", index: 0 },
      { droppableId: "completed", index: 0 },
    );
    expect(next).toBe(state);
  });
});

describe("applyServerTaskUpdate", () => {
  it("moves the task to the column matching the server's status", () => {
    const cols = emptyKanbanColumns();
    cols.up_next = [makeTask(1, "up_next"), makeTask(2, "up_next")];
    const updated = { ...makeTask(1, "blocked"), title: "Now blocked" };
    const next = applyServerTaskUpdate(cols, updated);
    expect(next.up_next.map(t => t.id)).toEqual([2]);
    expect(next.blocked.map(t => t.id)).toEqual([1]);
    expect(next.blocked[0].title).toBe("Now blocked");
  });

  it("inserts a brand-new task into the right column even if not previously seen", () => {
    const cols = emptyKanbanColumns();
    const newTask = makeTask(99, "in_progress");
    const next = applyServerTaskUpdate(cols, newTask);
    expect(next.in_progress.map(t => t.id)).toEqual([99]);
  });
});
