"use client";

import { useState } from "react";

import { TimeDisplay } from "@/app/components/TimeDisplay";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function TaskNotes({
  taskId,
  initialDescription,
  updatedAt,
}: {
  taskId: number;
  initialDescription: string;
  updatedAt: string;
}) {
  const [value, setValue] = useState(initialDescription);
  const [saved, setSaved] = useState(initialDescription);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(updatedAt);

  async function save() {
    const trimmed = value.trim();
    if (trimmed === saved) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: trimmed }),
      });
      if (res.ok) {
        const task = await res.json();
        setSaved(trimmed);
        setLastSavedAt(task.updated_at);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack-sm">
      <h3>Notes</h3>
      <textarea
        className="task-notes-input"
        rows={3}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        placeholder="Add notes about this task..."
      />
      {saving && <span className="small">Saving...</span>}
      {!saving && value.trim() !== saved && (
        <span className="small" style={{ color: "var(--text-tertiary)" }}>
          Unsaved changes
        </span>
      )}
      {!saving && value.trim() === saved && saved && (
        <span className="small" style={{ color: "var(--text-tertiary)" }}>
          Last saved <TimeDisplay iso={lastSavedAt} />
        </span>
      )}
    </div>
  );
}
