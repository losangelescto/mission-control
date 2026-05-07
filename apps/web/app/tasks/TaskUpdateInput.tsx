"use client";

import { useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { TimeDisplay } from "@/app/components/TimeDisplay";
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <textarea
          className="task-notes-input"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Add an update…"
        />
        <div>
          <BigButton
            kind="secondary"
            type="submit"
            disabled={submitting || !text.trim()}
          >
            {submitting ? "Posting…" : "Post update"}
          </BigButton>
        </div>
      </form>
      {updates.length > 0 ? (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {updates.map((u) => (
            <li
              key={u.id}
              style={{
                padding: "12px 16px",
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: 6,
              }}
            >
              <div style={{ fontSize: 15, color: "var(--ink)", lineHeight: 1.5 }}>{u.summary}</div>
              <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 4 }}>
                {u.created_by} · <TimeDisplay iso={u.created_at} />
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
