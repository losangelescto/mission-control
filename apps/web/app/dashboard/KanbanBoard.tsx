"use client";

import {
  DragDropContext,
  Draggable,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PriorityFlag } from "@/app/components/PriorityFlag";
import { StatusPill } from "@/app/components/StatusPill";
import { BlockTaskDialog } from "@/app/tasks/BlockTaskDialog";
import { UnblockTaskDialog } from "@/app/tasks/UnblockTaskDialog";
import type { Task, TaskStatus } from "@/lib/api/types";
import {
  applyServerTaskUpdate,
  groupTasksByStatus,
  moveTask,
  type KanbanColumns,
} from "@/lib/kanban-reducer";
import { formatTaskDue } from "@/lib/time-display";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLUMNS: ReadonlyArray<{ key: TaskStatus; label: string }> = [
  { key: "up_next",     label: "Up Next"     },
  { key: "in_progress", label: "In Progress" },
  { key: "blocked",     label: "Blocked"     },
  { key: "completed",   label: "Completed"   },
  { key: "backlog",     label: "Backlog"     },
] as const;

type PendingDialog =
  | { kind: "block"; taskId: number; task: Task }
  | { kind: "unblock"; taskId: number; task: Task; nextStatus: TaskStatus };

export function KanbanBoard({ initialTasks }: { initialTasks: Task[] }) {
  const router = useRouter();
  const [columns, setColumns] = useState<KanbanColumns>(() => groupTasksByStatus(initialTasks));
  const [mounted, setMounted] = useState(false);
  const [mobileActiveCol, setMobileActiveCol] = useState<TaskStatus>("up_next");
  const [dialog, setDialog] = useState<PendingDialog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => setMounted(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  const onDragEnd = useCallback(
    async (result: DropResult) => {
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

      // Drag-into-blocked needs an obstacle captured. Open the existing
      // BlockTaskDialog instead of silently PATCHing. We do NOT optimistic-
      // move first — the card stays in its source column until the dialog
      // confirms (or returns to source if cancelled).
      if (dstKey === "blocked" && srcKey !== "blocked") {
        const sourceList = columns[srcKey] ?? [];
        const task = sourceList[source.index];
        if (!task) return;
        setDialog({ kind: "block", taskId, task });
        return;
      }

      // Drag-out-of-blocked needs resolution notes. Open UnblockTaskDialog.
      if (srcKey === "blocked" && dstKey !== "blocked") {
        const sourceList = columns[srcKey] ?? [];
        const task = sourceList[source.index];
        if (!task) return;
        setDialog({ kind: "unblock", taskId, task, nextStatus: dstKey });
        return;
      }

      // Normal cross-column move (or same-column reorder). Optimistic
      // update + PATCH, with rollback on failure.
      const previousColumns = columns;
      const nextColumns = moveTask(columns, source, destination);
      setColumns(nextColumns);
      setError(null);

      if (srcKey === dstKey) return; // same-column reorder is local-only

      try {
        const res = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: dstKey }),
        });
        if (!res.ok) throw new Error(`PATCH failed (${res.status})`);
        // Refetch the page on success so server-derived fields like
        // completed_at / updated_at and the Suggested-tasks badge sync.
        router.refresh();
      } catch (e) {
        // Roll back the optimistic move and surface a quiet inline error.
        setColumns(previousColumns);
        setError(e instanceof Error ? e.message : "Could not save the change. Try again.");
      }
    },
    [columns, router],
  );

  // Block/unblock dialog success handlers. The dialog already POSTed and
  // the API returned an updated task status of 'blocked' (block flow) or
  // whatever next_status was passed (unblock flow). We move the card
  // locally to match, then router.refresh() to sync the rest of the page.
  const onBlocked = useCallback(() => {
    if (dialog?.kind !== "block") return;
    const blockedTask: Task = { ...dialog.task, status: "blocked" };
    setColumns(prev => applyServerTaskUpdate(prev, blockedTask));
    setDialog(null);
    router.refresh();
  }, [dialog, router]);

  const onUnblocked = useCallback(() => {
    if (dialog?.kind !== "unblock") return;
    const unblockedTask: Task = { ...dialog.task, status: dialog.nextStatus };
    setColumns(prev => applyServerTaskUpdate(prev, unblockedTask));
    setDialog(null);
    router.refresh();
  }, [dialog, router]);

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
      {/* Mobile-only tab strip */}
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
                              data-testid={`kanban-card-${task.id}`}
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

      {/* Quiet running total */}
      <div className="kanban-total" aria-live="polite">
        {totalCount} task{totalCount === 1 ? "" : "s"}
      </div>

      {/* Inline error pill — appears when a PATCH fails after optimistic
          update; the moved card has already snapped back to its source
          column via the rollback path in onDragEnd. */}
      {error ? (
        <div
          role="alert"
          style={{
            marginTop: 12,
            padding: "10px 14px",
            background: "color-mix(in oklch, var(--danger) 14%, transparent)",
            color: "var(--danger)",
            border: "1px solid var(--danger)",
            borderRadius: 6,
            fontSize: 14,
          }}
        >
          {error}
        </div>
      ) : null}

      {/* Dialogs — open programmatically when drag-drop crosses the
          blocked column boundary. */}
      {dialog?.kind === "block" ? (
        <BlockTaskDialog
          taskId={dialog.taskId}
          onClose={() => setDialog(null)}
          onBlocked={onBlocked}
        />
      ) : null}
      {dialog?.kind === "unblock" ? (
        <UnblockTaskDialog
          taskId={dialog.taskId}
          onClose={() => setDialog(null)}
          onUnblocked={onUnblocked}
        />
      ) : null}
    </DragDropContext>
  );
}
