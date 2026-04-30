"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
    <div className="stack-sm">
      <div className="meta-row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Sub-Tasks</h3>
        <span className="small" style={{ color: "var(--text-tertiary)" }}>
          {total === 0 ? "None yet" : `${completed} of ${total} completed`}
        </span>
      </div>

      {subTasks.length > 0 ? (
        <ul className="list">
          {subTasks.map((s) => (
            <li key={s.id}>
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.5rem",
                }}
              >
                <input
                  type="checkbox"
                  checked={s.status === "completed"}
                  onChange={() => toggleStatus(s)}
                  disabled={busy === `toggle-${s.id}`}
                  style={{
                    width: "auto",
                    height: "auto",
                    marginTop: "0.25rem",
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: "0.9375rem" }}>
                    {s.title}
                  </div>
                  {s.description ? (
                    <div className="small" style={{ marginTop: "0.25rem" }}>
                      {s.description}
                    </div>
                  ) : null}
                  <div
                    className="meta-row"
                    style={{ marginTop: "0.375rem", flexWrap: "wrap" }}
                  >
                    <span data-status={s.status}>{s.status.replace("_", " ")}</span>
                    {s.canon_reference ? (
                      <span className="badge">{s.canon_reference}</span>
                    ) : null}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setPendingDelete(s)}
                  disabled={busy === `delete-${s.id}`}
                  style={{
                    flexShrink: 0,
                    padding: "0.25rem 0.5rem",
                    minHeight: "auto",
                    fontSize: "0.75rem",
                    background: "transparent",
                    border: "1px solid var(--border-input)",
                    borderRadius: "var(--radius)",
                    color: "var(--text-tertiary)",
                    cursor: "pointer",
                    width: "auto",
                    height: "auto",
                  }}
                  aria-label="Delete sub-task"
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {drafts ? (
        <article
          className="panel"
          style={{ background: "var(--bg-base)", padding: "0.875rem" }}
        >
          <h3 style={{ marginBottom: "0.5rem" }}>
            Generated preview ({drafts.length - deselectedDrafts.size} of {drafts.length} selected)
          </h3>
          <p className="small" style={{ marginBottom: "0.5rem", color: "var(--text-tertiary)" }}>
            Uncheck any draft you don&apos;t want before saving.
          </p>
          <ul className="list">
            {drafts.map((d, i) => {
              const selected = !deselectedDrafts.has(i);
              return (
                <li key={`${d.title}-${i}`}>
                  <label
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      alignItems: "flex-start",
                      cursor: "pointer",
                      opacity: selected ? 1 : 0.5,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() =>
                        setDeselectedDrafts((prev) => toggleIndex(prev, i))
                      }
                      aria-label={`Include draft: ${d.title}`}
                      style={{ width: "auto", height: "auto", marginTop: "0.25rem", flexShrink: 0 }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: "0.9375rem" }}>
                        {d.title}
                      </div>
                      {d.description ? (
                        <div className="small" style={{ marginTop: "0.25rem" }}>
                          {d.description}
                        </div>
                      ) : null}
                      {d.canon_reference ? (
                        <span className="badge" style={{ marginTop: "0.25rem" }}>
                          {d.canon_reference}
                        </span>
                      ) : null}
                    </div>
                  </label>
                </li>
              );
            })}
          </ul>
          <div className="cta-row">
            <button
              type="button"
              className="link-btn"
              onClick={saveAllDrafts}
              disabled={busy === "save-all" || drafts.length === deselectedDrafts.size}
            >
              {busy === "save-all"
                ? "Saving..."
                : `Save ${drafts.length - deselectedDrafts.size}`}
            </button>
            <button
              type="button"
              onClick={() => {
                setDrafts(null);
                setDeselectedDrafts(new Set());
              }}
              style={{
                background: "transparent",
                border: "1px solid var(--border-input)",
                borderRadius: "var(--radius)",
                color: "var(--text-secondary)",
                cursor: "pointer",
                padding: "0 1rem",
                height: 44,
                fontFamily: "inherit",
                fontWeight: 600,
                width: "auto",
              }}
            >
              Discard
            </button>
          </div>
        </article>
      ) : null}

      {addOpen ? (
        <form onSubmit={addSubTask} className="stack-sm">
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
            placeholder="Aligned Standard (e.g. Consistency)"
            value={newCanonRef}
            onChange={(e) => setNewCanonRef(e.target.value)}
          />
          <div className="cta-row">
            <button
              type="submit"
              className="link-btn"
              disabled={busy === "create" || !newTitle.trim()}
            >
              {busy === "create" ? "Saving..." : "Add"}
            </button>
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              style={{
                background: "transparent",
                border: "1px solid var(--border-input)",
                borderRadius: "var(--radius)",
                color: "var(--text-secondary)",
                cursor: "pointer",
                padding: "0 1rem",
                height: 44,
                fontFamily: "inherit",
                fontWeight: 600,
                width: "auto",
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="cta-row">
          <button
            type="button"
            className="link-btn"
            onClick={() => setAddOpen(true)}
            disabled={busy !== null}
          >
            Add Sub-Task
          </button>
          <button
            type="button"
            onClick={generate}
            disabled={busy !== null}
            style={{
              background: "transparent",
              border: "1px solid var(--border-input)",
              borderRadius: "var(--radius)",
              color: "var(--text-secondary)",
              cursor: "pointer",
              padding: "0 1rem",
              height: 44,
              fontFamily: "inherit",
              fontWeight: 600,
              width: "auto",
            }}
          >
            {busy === "generate" ? "Generating..." : "Generate Sub-Tasks"}
          </button>
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
