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

  // Save status: blank when idle, italic ink-faint while saving / unsaved,
  // and a quiet "last saved" timestamp once persisted. The DetailSection
  // wrapper (Description) provides the section heading, so we don't repeat
  // a title here.
  let status: React.ReactNode = null;
  if (saving) {
    status = "Saving…";
  } else if (value.trim() !== saved) {
    status = "Unsaved changes";
  } else if (saved) {
    status = (
      <>
        Last saved <TimeDisplay iso={lastSavedAt} />
      </>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <textarea
        className="task-notes-input"
        rows={3}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        placeholder="Add notes about this task…"
      />
      {status ? (
        <span style={{ fontSize: 13, color: "var(--ink-faint)", fontStyle: "italic" }}>
          {status}
        </span>
      ) : null}
    </div>
  );
}
