"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { BigCheckbox } from "@/app/components/BigCheckbox";
import { ConfirmDialog } from "@/app/components/ConfirmDialog";
import { SubTask, SubTaskDraft } from "@/lib/api/types";
import { pickSelectedDrafts, toggleIndex } from "@/lib/subtask-drafts";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Props = {
  taskId: number;
  initialSubTasks: SubTask[];
};

function nextStatus(status: SubTask["status"]): SubTask["status"] {
  if (status === "pending") return "in_progress";
  if (status === "in_progress") return "completed";
  return "pending";
}

// Subtle status hint for in-progress / pending subtasks. Completed gets
// strikethrough via the BigCheckbox label, so no extra pill needed there.
const SUBTASK_STATUS_LABEL: Record<SubTask["status"], string> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
};

const SUBTASK_STATUS_TINT: Record<SubTask["status"], string> = {
  pending: "var(--ink-faint)",
  in_progress: "var(--success)",
  completed: "var(--ink-faint)",
};

export function SubTasks({ taskId, initialSubTasks }: Props) {
  const router = useRouter();
  const [subTasks, setSubTasks] = useState<SubTask[]>(initialSubTasks);
  const [addOpen, setAddOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCanonRef, setNewCanonRef] = useState("");
  const [drafts, setDrafts] = useState<SubTaskDraft[] | null>(null);
  const [deselectedDrafts, setDeselectedDrafts] = useState<Set<number>>(
    () => new Set(),
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<SubTask | null>(null);

  const completed = subTasks.filter((s) => s.status === "completed").length;
  const total = subTasks.length;

  async function toggleStatus(s: SubTask) {
    const next = nextStatus(s.status);
    setBusy(`toggle-${s.id}`);
    try {
      const res = await fetch(`${API_BASE_URL}/subtasks/${s.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      if (res.ok) {
        const updated: SubTask = await res.json();
        setSubTasks((prev) => prev.map((x) => (x.id === s.id ? updated : x)));
      }
    } finally {
      setBusy(null);
    }
  }

  async function confirmRemoveSubTask() {
    const s = pendingDelete;
    if (!s) return;
    setBusy(`delete-${s.id}`);
    try {
      await fetch(`${API_BASE_URL}/subtasks/${s.id}`, { method: "DELETE" });
      setSubTasks((prev) => prev.filter((x) => x.id !== s.id));
      setPendingDelete(null);
    } finally {
      setBusy(null);
    }
  }

  async function addSubTask(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setBusy("create");
    try {
      const res = await fetch(`${API_BASE_URL}/tasks/${taskId}/subtasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTitle.trim(),
          description: newDescription.trim(),
          canon_reference: newCanonRef.trim(),
        }),
      });
      if (res.ok) {
        const created: SubTask = await res.json();
        setSubTasks((prev) => [...prev, created]);
        setNewTitle("");
        setNewDescription("");
        setNewCanonRef("");
        setAddOpen(false);
      }
    } finally {
      setBusy(null);
    }
  }

  async function generate() {
    setBusy("generate");
    try {
      const res = await fetch(
        `${API_BASE_URL}/tasks/${taskId}/subtasks/generate`,
        { method: "POST" },
      );
      if (res.ok) {
        const body = await res.json();
        setDrafts(body.drafts);
        setDeselectedDrafts(new Set());
      }
    } finally {
      setBusy(null);
    }
  }

  async function saveAllDrafts() {
    if (!drafts) return;
    const toSave = pickSelectedDrafts(drafts, deselectedDrafts);
    if (toSave.length === 0) {
      setDrafts(null);
      setDeselectedDrafts(new Set());
      return;
    }
    setBusy("save-all");
    try {
      for (const d of toSave) {
        const res = await fetch(`${API_BASE_URL}/tasks/${taskId}/subtasks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(d),
        });
        if (res.ok) {
          const created: SubTask = await res.json();
          setSubTasks((prev) => [...prev, created]);
        }
      }
      setDrafts(null);
      setDeselectedDrafts(new Set());
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ fontSize: 13, color: "var(--ink-faint)" }}>
          {total === 0 ? "None yet" : `${completed} of ${total} completed`}
        </span>
      </div>

      {subTasks.length > 0 ? (
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
          {subTasks.map((s) => {
            const completedStep = s.status === "completed";
            return (
              <li
                key={s.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  padding: "12px 16px",
                  background: "var(--surface)",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                }}
              >
                <BigCheckbox
                  checked={completedStep}
                  onChange={() => toggleStatus(s)}
                  disabled={busy === `toggle-${s.id}`}
                  label={
                    <span
                      style={{
                        fontSize: 16,
                        fontWeight: 500,
                        color: completedStep ? "var(--ink-faint)" : "var(--ink)",
                        textDecoration: completedStep ? "line-through" : "none",
                      }}
                    >
                      {s.title}
                    </span>
                  }
                />
                <div style={{ flex: 1, minWidth: 0, marginTop: 2 }}>
                  {s.description ? (
                    <div style={{ fontSize: 14, color: "var(--ink-soft)", marginTop: 4, marginLeft: 34 }}>
                      {s.description}
                    </div>
                  ) : null}
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 10,
                      marginTop: 6,
                      marginLeft: 34,
                      fontSize: 12,
                      color: "var(--ink-faint)",
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                    }}
                  >
                    {!completedStep ? (
                      <span style={{ color: SUBTASK_STATUS_TINT[s.status] }}>
                        {SUBTASK_STATUS_LABEL[s.status]}
                      </span>
                    ) : null}
                    {s.canon_reference ? <span>{s.canon_reference}</span> : null}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setPendingDelete(s)}
                  disabled={busy === `delete-${s.id}`}
                  aria-label={`Delete sub-task: ${s.title}`}
                  style={{
                    flexShrink: 0,
                    width: 28,
                    height: 28,
                    padding: 0,
                    background: "transparent",
                    border: "1px solid var(--line)",
                    borderRadius: 3,
                    color: "var(--ink-faint)",
                    cursor: "pointer",
                    fontSize: 16,
                    lineHeight: 1,
                    transition: "color 120ms ease, border-color 120ms ease",
                  }}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {drafts ? (
        <article
          style={{
            background: "var(--surface)",
            border: "2px solid var(--brass)",
            borderRadius: 8,
            padding: "20px 22px",
          }}
        >
          <div style={{ fontSize: 16, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>
            Generated preview · {drafts.length - deselectedDrafts.size} of {drafts.length} selected
          </div>
          <p style={{ fontSize: 14, color: "var(--ink-soft)", margin: "0 0 12px" }}>
            Uncheck any draft you don&apos;t want before saving.
          </p>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {drafts.map((d, i) => {
              const selected = !deselectedDrafts.has(i);
              return (
                <li
                  key={`${d.title}-${i}`}
                  style={{
                    padding: "10px 14px",
                    background: "var(--surface-raised)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    opacity: selected ? 1 : 0.55,
                    transition: "opacity 120ms ease",
                  }}
                >
                  <BigCheckbox
                    checked={selected}
                    onChange={() => setDeselectedDrafts((prev) => toggleIndex(prev, i))}
                    label={
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 15, fontWeight: 500, color: "var(--ink)" }}>
                          {d.title}
                        </span>
                        {d.description ? (
                          <span style={{ fontSize: 13, color: "var(--ink-soft)", fontWeight: 400 }}>
                            {d.description}
                          </span>
                        ) : null}
                        {d.canon_reference ? (
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 600,
                              letterSpacing: "0.04em",
                              textTransform: "uppercase",
                              color: "var(--brass-deep)",
                              marginTop: 2,
                            }}
                          >
                            {d.canon_reference}
                          </span>
                        ) : null}
                      </div>
                    }
                  />
                </li>
              );
            })}
          </ul>
          <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
            <BigButton
              kind="primary"
              onClick={saveAllDrafts}
              disabled={busy === "save-all" || drafts.length === deselectedDrafts.size}
            >
              {busy === "save-all" ? "Saving…" : `Save ${drafts.length - deselectedDrafts.size}`}
            </BigButton>
            <BigButton
              kind="secondary"
              onClick={() => {
                setDrafts(null);
                setDeselectedDrafts(new Set());
              }}
            >
              Discard
            </BigButton>
          </div>
        </article>
      ) : null}

      {addOpen ? (
        <form onSubmit={addSubTask} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <input
            type="text"
            placeholder="Title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            autoFocus
          />
          <textarea
            className="task-notes-input"
            rows={2}
            placeholder="What to do, why it matters, what done looks like"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
          <input
            type="text"
            placeholder="Aligned standard (e.g. Consistency)"
            value={newCanonRef}
            onChange={(e) => setNewCanonRef(e.target.value)}
          />
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <BigButton
              kind="primary"
              type="submit"
              disabled={busy === "create" || !newTitle.trim()}
            >
              {busy === "create" ? "Saving…" : "Add"}
            </BigButton>
            <BigButton
              kind="secondary"
              onClick={() => setAddOpen(false)}
            >
              Cancel
            </BigButton>
          </div>
        </form>
      ) : (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <BigButton
            kind="secondary"
            onClick={() => setAddOpen(true)}
            disabled={busy !== null}
          >
            Add sub-task
          </BigButton>
          <BigButton
            kind="quiet"
            onClick={generate}
            disabled={busy !== null}
          >
            {busy === "generate" ? "Generating…" : "Generate sub-tasks"}
          </BigButton>
        </div>
      )}

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        title="Delete sub-task?"
        body={
          pendingDelete ? (
            <>Delete <strong>{pendingDelete.title}</strong>? This cannot be undone.</>
          ) : null
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="destructive"
        busy={pendingDelete !== null && busy === `delete-${pendingDelete.id}`}
        onConfirm={confirmRemoveSubTask}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
