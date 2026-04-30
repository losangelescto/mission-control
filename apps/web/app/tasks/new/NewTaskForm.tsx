"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiClient } from "@/lib/api/client";
import type { TaskStatus } from "@/lib/api/types";

const SEVEN_STANDARDS = [
  "Anticipation",
  "Recognition",
  "Consistency",
  "Accountability",
  "Emotional Intelligence",
  "Ownership",
  "Elevation",
] as const;

const STATUS_OPTIONS: TaskStatus[] = [
  "backlog",
  "up_next",
  "in_progress",
  "blocked",
  "completed",
];

const PRIORITY_OPTIONS = ["low", "medium", "high"] as const;

function defaultDueDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return d.toISOString().slice(0, 10);
}

export default function NewTaskForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    const fd = new FormData(e.currentTarget);
    const dueAtRaw = fd.get("due_at") as string;
    const dueAtIso = dueAtRaw ? new Date(`${dueAtRaw}T00:00:00Z`).toISOString() : null;

    try {
      const created = await apiClient.createTask({
        title: (fd.get("title") as string).trim(),
        description: (fd.get("description") as string).trim(),
        objective: (fd.get("objective") as string).trim(),
        standard: fd.get("standard") as string,
        status: fd.get("status") as TaskStatus,
        priority: fd.get("priority") as string,
        owner_name: (fd.get("owner_name") as string).trim(),
        assigner_name: (fd.get("assigner_name") as string).trim() || "self",
        due_at: dueAtIso,
        source_confidence: 1.0,
      });
      router.push(`/tasks?selected=${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="stack-sm">
      <label className="stack-sm">
        <span>Title</span>
        <input
          name="title"
          type="text"
          required
          minLength={1}
          maxLength={200}
          placeholder="Short imperative — what's the move"
        />
      </label>

      <label className="stack-sm">
        <span>Description</span>
        <textarea
          name="description"
          required
          maxLength={4000}
          rows={4}
          placeholder="What's going on, what's at stake, what's been tried"
        />
      </label>

      <label className="stack-sm">
        <span>Objective</span>
        <input
          name="objective"
          type="text"
          required
          maxLength={500}
          placeholder="One sentence — the outcome that defines done"
        />
      </label>

      <label className="stack-sm">
        <span>Standard</span>
        <select name="standard" required defaultValue="Accountability">
          {SEVEN_STANDARDS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <div className="grid cols-2" style={{ gap: "0.75rem" }}>
        <label className="stack-sm">
          <span>Owner</span>
          <input name="owner_name" type="text" required placeholder="Who's executing" />
        </label>
        <label className="stack-sm">
          <span>Assigner</span>
          <input
            name="assigner_name"
            type="text"
            defaultValue="self"
            placeholder="Who asked for it"
          />
        </label>
      </div>

      <div className="grid cols-2" style={{ gap: "0.75rem" }}>
        <label className="stack-sm">
          <span>Status</span>
          <select name="status" required defaultValue="up_next">
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="stack-sm">
          <span>Priority</span>
          <select name="priority" required defaultValue="medium">
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="stack-sm">
        <span>Due date</span>
        <input name="due_at" type="date" defaultValue={defaultDueDate()} />
      </label>

      {error ? (
        <div className="small" role="alert" style={{ color: "#991b1b" }}>
          {error}
        </div>
      ) : null}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create Task"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/tasks")}
          disabled={submitting}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
