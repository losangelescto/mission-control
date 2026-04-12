"use client";

import { useState } from "react";
import { TaskUpdate } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function TaskUpdateInput({
  taskId,
  initialUpdates,
}: {
  taskId: number;
  initialUpdates: TaskUpdate[];
}) {
  const [updates, setUpdates] = useState<TaskUpdate[]>(initialUpdates);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const summary = text.trim();
    if (!summary) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/tasks/${taskId}/updates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          update_type: "note",
          summary,
          what_happened: summary,
          options_considered: "",
          steps_taken: "",
          next_step: "",
          created_by: "user",
        }),
      });
      if (res.ok) {
        const created: TaskUpdate = await res.json();
        setUpdates((prev) => [created, ...prev]);
        setText("");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function formatTimestamp(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return (
    <div className="stack-sm">
      <h3>Updates</h3>
      <form onSubmit={handleSubmit} className="stack-sm">
        <textarea
          className="task-notes-input"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Add an update..."
        />
        <div>
          <button
            type="submit"
            className="link-btn"
            disabled={submitting || !text.trim()}
            style={{ opacity: submitting || !text.trim() ? 0.5 : 1 }}
          >
            {submitting ? "Posting..." : "Post Update"}
          </button>
        </div>
      </form>
      {updates.length > 0 && (
        <ul className="list">
          {updates.map((u) => (
            <li key={u.id}>
              <div style={{ fontSize: "0.9375rem" }}>{u.summary}</div>
              <div className="small" style={{ marginTop: "0.125rem" }}>
                {u.created_by} &middot; {formatTimestamp(u.created_at)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
