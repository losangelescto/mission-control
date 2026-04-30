"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DragDropContext,
  Droppable,
  Draggable,
  type DropResult,
} from "@hello-pangea/dnd";
import Link from "next/link";
import { Task } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLUMNS = [
  { key: "up_next", label: "Up Next" },
  { key: "in_progress", label: "In Progress" },
  { key: "blocked", label: "Blocked" },
  { key: "completed", label: "Completed" },
  { key: "backlog", label: "Backlog" },
] as const;

function formatDue(due: string | null): string {
  if (!due) return "—";
  const d = new Date(due);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).trimEnd() + "…";
}

function groupTasks(tasks: Task[]): Record<string, Task[]> {
  const grouped: Record<string, Task[]> = {};
  for (const col of COLUMNS) grouped[col.key] = [];
  for (const task of tasks) {
    if (grouped[task.status]) grouped[task.status].push(task);
  }
  return grouped;
}

export function KanbanBoard({ initialTasks }: { initialTasks: Task[] }) {
  const [columns, setColumns] = useState(() => groupTasks(initialTasks));
  // @hello-pangea/dnd injects dynamic data-rfd-* ids and inline transform
  // styles into Draggable/Droppable on first client render — values that
  // cannot be reproduced server-side. To eliminate every hydration-mismatch
  // surface (React #418), we render an empty container during SSR and the
  // first client render, then upgrade to the live DnD tree once mounted.
  // The empty container preserves layout space until the kanban paints.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const onDragEnd = useCallback(
    async (result: DropResult) => {
      const { source, destination, draggableId } = result;
      if (!destination) return;
      if (
        source.droppableId === destination.droppableId &&
        source.index === destination.index
      )
        return;

      const taskId = parseInt(draggableId, 10);
      const srcKey = source.droppableId;
      const dstKey = destination.droppableId;

      // Optimistic update
      setColumns((prev) => {
        const next = { ...prev };
        const srcList = [...(prev[srcKey] ?? [])];
        const [moved] = srcList.splice(source.index, 1);
        if (!moved) return prev;

        const updated = { ...moved, status: dstKey as Task["status"] };

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
        await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: dstKey }),
        });
      }
    },
    []
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
      <div className="kanban">
        {COLUMNS.map((col) => (
          <Droppable key={col.key} droppableId={col.key}>
            {(provided) => (
              <div className="kanban-col">
                <Link
                  href={`/tasks?status=${col.key}`}
                  className="kanban-col-header"
                  data-status={col.key}
                >
                  <span className="kanban-col-title">{col.label}</span>
                  <span className="kanban-col-count">
                    {(columns[col.key] ?? []).length}
                  </span>
                </Link>
                <div
                  className="kanban-col-body"
                  ref={provided.innerRef}
                  {...provided.droppableProps}
                >
                  {(columns[col.key] ?? []).length === 0 ? (
                    <p className="kanban-empty">No tasks</p>
                  ) : (
                    (columns[col.key] ?? []).map((task, index) => (
                      <Draggable
                        key={task.id}
                        draggableId={String(task.id)}
                        index={index}
                      >
                        {(dragProvided) => (
                          <Link
                            href={`/tasks?status=${task.status}&selected=${task.id}`}
                            className="kanban-card"
                            ref={dragProvided.innerRef}
                            {...dragProvided.draggableProps}
                            {...dragProvided.dragHandleProps}
                          >
                            <div className="kanban-card-title">
                              {truncate(task.title, 60)}
                            </div>
                            <div className="kanban-card-desc">
                              {truncate(task.description, 80)}
                            </div>
                            <div className="kanban-card-meta">
                              <span>
                                <span className="kanban-card-label">Due</span>{" "}
                                {formatDue(task.due_at)}
                              </span>
                              <span>
                                <span className="kanban-card-label">Owner</span>{" "}
                                {task.owner_name}
                              </span>
                              <span>
                                <span className="kanban-card-label">
                                  Manager
                                </span>{" "}
                                {task.assigner_name}
                              </span>
                            </div>
                            <div className="kanban-card-footer">
                              <span data-status={task.status}>
                                {task.status.replace("_", " ")}
                              </span>
                              <span
                                className="badge"
                                style={{
                                  background: "var(--bg-hover)",
                                  color: "var(--text-secondary)",
                                }}
                              >
                                {task.priority}
                              </span>
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
        ))}
      </div>
    </DragDropContext>
  );
}
