import Link from "next/link";

import type { Task } from "@/lib/api/types";
import { formatTaskDue } from "@/lib/time-display";

import { PriorityFlag } from "./PriorityFlag";

/**
 * v2 'Calm' callout-card task row. Shown by the Dashboard inside CalloutGroup
 * sections (Blocked / In Progress / Up Next). Click navigates to the Tasks
 * route with the task pre-selected.
 *
 * Geometry / colors match /ui-update/Mission Control v2 - Calm.html line 511.
 * Hover affordance is owned by the .big-task-card CSS class so this stays a
 * server component (no useState / mouse handlers).
 */
export function BigTaskCard({ task }: { task: Task }) {
  const due = formatTaskDue(task.due_at);
  return (
    <Link
      href={`/tasks?status=${task.status}&selected=${task.id}`}
      className="big-task-card"
      style={{
        display: "block",
        padding: "20px 22px",
        background: "var(--surface)",
        border: "2px solid var(--line)",
        borderRadius: 8,
        color: "inherit",
        textDecoration: "none",
        transition: "border-color 120ms ease, background 120ms ease",
      }}
    >
      <div
        style={{
          fontSize: 19,
          fontWeight: 500,
          lineHeight: 1.35,
          color: "var(--ink)",
          marginBottom: 12,
        }}
      >
        {task.title}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 14,
          fontSize: 15,
          color: "var(--ink-soft)",
        }}
      >
        <PriorityFlag priority={task.priority} />
        <span>{task.owner_name}</span>
        <span aria-hidden="true" style={{ color: "var(--ink-faint)" }}>
          ·
        </span>
        <span style={{ color: due.overdue ? "var(--danger)" : "var(--ink-soft)" }}>
          {due.overdue ? "Overdue · " : "Due "}
          {due.text}
        </span>
      </div>
    </Link>
  );
}
