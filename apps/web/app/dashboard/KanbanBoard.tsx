"use client";

import {
  DragDropContext,
  Draggable,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PriorityFlag } from "@/app/components/PriorityFlag";
import { StatusPill } from "@/app/components/StatusPill";
import type { Task, TaskStatus } from "@/lib/api/types";
import { formatTaskDue } from "@/lib/time-display";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLUMNS: ReadonlyArray<{ key: TaskStatus; label: string }> = [
  { key: "up_next",     label: "Up Next"     },
  { key: "in_progress", label: "In Progress" },
  { key: "blocked",     label: "Blocked"     },
  { key: "completed",   label: "Completed"   },
  { key: "backlog",     label: "Backlog"     },
] as const;

function groupTasks(tasks: Task[]): Record<TaskStatus, Task[]> {
  const grouped = {
    up_next: [],
    in_progress: [],
    blocked: [],
    completed: [],
    backlog: [],
  } as Record<TaskStatus, Task[]>;
  for (const task of tasks) {
    if (grouped[task.status]) grouped[task.status].push(task);
  }
  return grouped;
}

export function KanbanBoard({ initialTasks }: { initialTasks: Task[] }) {
  const [columns, setColumns] = useState(() => groupTasks(initialTasks));
  // @hello-pangea/dnd injects dynamic data-rfd-* ids and inline transform
  // styles into Draggable / Droppable on first client render — values that
  // can't be reproduced server-side. Render an empty placeholder during
  // SSR and the first client paint, then upgrade to the live DnD tree
  // once mounted to eliminate React #418 hydration mismatches.
  const [mounted, setMounted] = useState(false);
  // Mobile (<900px) shows one column at a time with a tab strip.
  const [mobileActiveCol, setMobileActiveCol] = useState<TaskStatus>("up_next");

  useEffect(() => {
    // requestAnimationFrame lets the lint rule for set-state-in-effect
    // pass while still flipping mounted before first paint.
    const id = window.requestAnimationFrame(() => setMounted(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  const onDragEnd = useCallback(async (result: DropResult) => {
    const { source, destination, draggableId } = result;
    if (!destination) return;
    if (
      source.droppableId === destination.droppableId &&
      source.index === destination.index
    ) {
      return;
    }

    const taskId = parseInt(draggableId, 10);
    const srcKey = source.droppableId as TaskStatus;
    const dstKey = destination.droppableId as TaskStatus;

    // Optimistic update — the card lands in the new column instantly.
    setColumns(prev => {
      const next = { ...prev };
      const srcList = [...(prev[srcKey] ?? [])];
      const [moved] = srcList.splice(source.index, 1);
      if (!moved) return prev;
      const updated = { ...moved, status: dstKey };
      if (srcKey === dstKey) {
        srcList.splice(destination.index, 0, updated);
        next[srcKey] = srcList;
      } else {
        next[srcKey] = srcList;
        const dstList = [...(prev[dstKey] ?? [])];
        dstList.splice(destination.index, 0, updated);
        next[dstKey] = dstList;
      }
      return next;
    });

    if (srcKey !== dstKey) {
      // PR-B will integrate BlockTaskDialog / UnblockTaskDialog plus
      // rollback on failure. For now, the silent PATCH preserves the
      // old KanbanBoard behavior verbatim.
      await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: dstKey }),
      });
    }
  }, []);

  const totalCount = useMemo(
    () => COLUMNS.reduce((n, c) => n + (columns[c.key]?.length ?? 0), 0),
    [columns],
  );

  if (!mounted) {
    return (
      <div
        className="kanban"
        aria-busy="true"
        aria-label="Loading kanban board"
        suppressHydrationWarning
      />
    );
  }

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      {/* Mobile-only tab strip — switches which single column is visible
          at <900px. The 5 Droppables stay mounted (just hidden) so a
          drag-drop never lands on an unmounted target. */}
      <div className="kanban-mobile-tabs" role="tablist" aria-label="Kanban columns">
        {COLUMNS.map(col => {
          const count = columns[col.key]?.length ?? 0;
          const active = mobileActiveCol === col.key;
          return (
            <button
              key={col.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setMobileActiveCol(col.key)}
              className={`kanban-mobile-tab${active ? " kanban-mobile-tab-active" : ""}`}
            >
              {col.label}
              <span className="kanban-mobile-tab-count">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="kanban" data-mobile-active={mobileActiveCol}>
        {COLUMNS.map(col => {
          const colTasks = columns[col.key] ?? [];
          return (
            <Droppable key={col.key} droppableId={col.key}>
              {(provided, snapshot) => (
                <div
                  className="kanban-column"
                  data-column={col.key}
                  data-dragging-over={snapshot.isDraggingOver ? "true" : undefined}
                >
                  <Link
                    href={`/tasks?status=${col.key}`}
                    className="kanban-column-header"
                    aria-label={`${col.label} — ${colTasks.length} tasks. Open in Tasks.`}
                  >
                    <StatusPill status={col.key} />
                    <span style={{ flex: 1 }} />
                    <span className="kanban-column-count">{colTasks.length}</span>
                  </Link>

                  <div
                    className="kanban-column-body"
                    ref={provided.innerRef}
                    {...provided.droppableProps}
                  >
                    {colTasks.length === 0 ? (
                      <p className="kanban-empty serif">No tasks</p>
                    ) : (
                      colTasks.map((task, index) => (
                        <Draggable
                          key={task.id}
                          draggableId={String(task.id)}
                          index={index}
                        >
                          {(dragProvided, dragSnapshot) => (
                            <Link
                              href={`/tasks?selected=${task.id}`}
                              ref={dragProvided.innerRef}
                              {...dragProvided.draggableProps}
                              {...dragProvided.dragHandleProps}
                              className="kanban-card"
                              data-dragging={dragSnapshot.isDragging ? "true" : undefined}
                            >
                              <div className="kanban-card-title">{task.title}</div>
                              <div className="kanban-card-meta">
                                <PriorityFlag priority={task.priority} />
                                <span className="kanban-card-owner">{task.owner_name}</span>
                                <span aria-hidden="true" className="kanban-card-sep">·</span>
                                {(() => {
                                  const due = formatTaskDue(task.due_at);
                                  return (
                                    <span
                                      className={due.overdue ? "kanban-card-due-overdue" : "kanban-card-due"}
                                    >
                                      {due.overdue ? "Overdue · " : "Due "}{due.text}
                                    </span>
                                  );
                                })()}
                              </div>
                            </Link>
                          )}
                        </Draggable>
                      ))
                    )}
                    {provided.placeholder}
                  </div>
                </div>
              )}
            </Droppable>
          );
        })}
      </div>

      {/* Quiet running total below the board — useful when several
          columns are visible at once on desktop. */}
      <div className="kanban-total" aria-live="polite">
        {totalCount} task{totalCount === 1 ? "" : "s"}
      </div>
    </DragDropContext>
  );
}
