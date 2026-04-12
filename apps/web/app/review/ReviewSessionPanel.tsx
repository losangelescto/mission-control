"use client";

import { useEffect, useRef, useState } from "react";
import { ReviewSession, Task, TaskUpdate } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function ReviewSessionPanel({
  tasks,
  owners,
  initialReviews,
  initialTaskId,
  initialOwner,
}: {
  tasks: Task[];
  owners: string[];
  initialReviews: ReviewSession[];
  initialTaskId?: number | null;
  initialOwner?: string | null;
}) {
  const [mode, setMode] = useState<"task" | "person">(
    initialOwner && !initialTaskId ? "person" : "task"
  );
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(initialTaskId ?? null);
  const [selectedOwner, setSelectedOwner] = useState<string>(initialOwner ?? "");
  const [reviews, setReviews] = useState<ReviewSession[]>(initialReviews);
  const [taskUpdates, setTaskUpdates] = useState<TaskUpdate[]>([]);

  // Form state
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [actionItems, setActionItems] = useState("");
  const [cadenceType, setCadenceType] = useState("ad_hoc");
  const [nextReviewDate, setNextReviewDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const notesRef = useRef<HTMLTextAreaElement>(null);
  const didAutoSelect = useRef(false);

  async function loadReviews(taskId: number | null, owner: string) {
    const params = new URLSearchParams();
    if (taskId) params.set("task_id", String(taskId));
    if (owner) params.set("owner", owner);
    const query = params.toString();
    try {
      const res = await fetch(
        `${API_BASE_URL}/reviews${query ? `?${query}` : ""}`
      );
      if (res.ok) {
        const data: ReviewSession[] = await res.json();
        setReviews(data);
      }
    } catch {
      /* silent */
    }
  }

  async function loadTaskUpdates(taskId: number) {
    try {
      const res = await fetch(`${API_BASE_URL}/tasks/${taskId}/updates`);
      if (res.ok) setTaskUpdates(await res.json());
    } catch {
      /* silent */
    }
  }

  // Auto-load data when initial selection comes from URL params
  useEffect(() => {
    if (didAutoSelect.current) return;
    didAutoSelect.current = true;

    if (initialTaskId) {
      Promise.all([loadReviews(initialTaskId, ""), loadTaskUpdates(initialTaskId)]).then(() => {
        // Scroll and focus after data loads
        setTimeout(() => {
          document.getElementById("review-session")?.scrollIntoView({ behavior: "smooth", block: "start" });
          setTimeout(() => notesRef.current?.focus(), 400);
        }, 100);
      });
    } else if (initialOwner) {
      loadReviews(null, initialOwner).then(() => {
        setTimeout(() => {
          document.getElementById("review-session")?.scrollIntoView({ behavior: "smooth", block: "start" });
          setTimeout(() => notesRef.current?.focus(), 400);
        }, 100);
      });
    }
  }, [initialTaskId, initialOwner]);

  async function onSelectTask(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value ? parseInt(e.target.value, 10) : null;
    setSelectedTaskId(id);
    setSelectedOwner("");
    if (id) {
      await Promise.all([loadReviews(id, ""), loadTaskUpdates(id)]);
    } else {
      setReviews([]);
      setTaskUpdates([]);
    }
  }

  async function onSelectOwner(e: React.ChangeEvent<HTMLSelectElement>) {
    const owner = e.target.value;
    setSelectedOwner(owner);
    setSelectedTaskId(null);
    setTaskUpdates([]);
    if (owner) {
      await loadReviews(null, owner);
    } else {
      setReviews([]);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!notes.trim() || !reviewer.trim()) return;
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        reviewer: reviewer.trim(),
        notes: notes.trim(),
        action_items: actionItems.trim(),
        cadence_type: cadenceType,
      };
      if (mode === "task" && selectedTaskId) body.task_id = selectedTaskId;
      if (mode === "person" && selectedOwner) body.owner_name = selectedOwner;
      if (nextReviewDate) body.next_review_date = nextReviewDate;

      const res = await fetch(`${API_BASE_URL}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const created: ReviewSession = await res.json();
        setReviews((prev) => [created, ...prev]);
        setNotes("");
        setActionItems("");
        setCadenceType("ad_hoc");
        setNextReviewDate("");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const selectedTask = selectedTaskId
    ? tasks.find((t) => t.id === selectedTaskId)
    : null;

  return (
    <div className="stack">
      {/* Mode tabs */}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button
          className="link-btn"
          onClick={() => {
            setMode("task");
            setSelectedOwner("");
            setReviews([]);
            setTaskUpdates([]);
          }}
          style={{
            opacity: mode === "task" ? 1 : 0.5,
            padding: "0.375rem 0.75rem",
            minHeight: "auto",
            fontSize: "0.875rem",
          }}
        >
          Review by Task
        </button>
        <button
          className="link-btn"
          onClick={() => {
            setMode("person");
            setSelectedTaskId(null);
            setReviews([]);
            setTaskUpdates([]);
          }}
          style={{
            opacity: mode === "person" ? 1 : 0.5,
            padding: "0.375rem 0.75rem",
            minHeight: "auto",
            fontSize: "0.875rem",
          }}
        >
          Review by Person
        </button>
      </div>

      {/* Selector */}
      <div>
        {mode === "task" ? (
          <select
            value={selectedTaskId ?? ""}
            onChange={onSelectTask}
            style={{ width: "100%" }}
          >
            <option value="">Select a task to review...</option>
            {tasks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title} ({t.status}) — {t.owner_name}
              </option>
            ))}
          </select>
        ) : (
          <select
            value={selectedOwner}
            onChange={onSelectOwner}
            style={{ width: "100%" }}
          >
            <option value="">Select a person to review...</option>
            {owners.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Task context */}
      {selectedTask && (
        <article className="panel">
          <h3>Task Context</h3>
          <div className="stack-sm">
            <div>
              <strong>{selectedTask.title}</strong>
            </div>
            <div className="small">
              Status: <span data-status={selectedTask.status}>{selectedTask.status}</span>
              {" · "}Owner: {selectedTask.owner_name}
              {" · "}Priority: {selectedTask.priority}
            </div>
            <div className="small">{selectedTask.description}</div>
            {taskUpdates.length > 0 && (
              <details open>
                <summary>
                  Task Updates ({taskUpdates.length})
                </summary>
                <div style={{ padding: "0.5rem 0.75rem" }}>
                  {taskUpdates.map((u) => (
                    <div
                      key={u.id}
                      style={{
                        padding: "0.375rem 0",
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      <div style={{ fontSize: "0.9375rem" }}>{u.summary}</div>
                      <div className="small">
                        {u.created_by} · {formatDate(u.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        </article>
      )}

      {/* New review entry form */}
      {(selectedTaskId || selectedOwner) && (
        <article className="panel">
          <h3>New Review Entry</h3>
          <form onSubmit={onSubmit} className="stack-sm">
            <input
              type="text"
              placeholder="Reviewer name"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
            />
            <textarea
              ref={notesRef}
              className="task-notes-input"
              rows={3}
              placeholder="Discussion notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <textarea
              className="task-notes-input"
              rows={2}
              placeholder="Action items..."
              value={actionItems}
              onChange={(e) => setActionItems(e.target.value)}
            />
            <div className="small" style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                Cadence:
                <select
                  value={cadenceType}
                  onChange={(e) => setCadenceType(e.target.value)}
                  style={{ width: "auto", height: "auto", padding: "0.25rem 0.5rem", fontSize: "0.875rem" }}
                >
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="ad_hoc">Ad Hoc</option>
                </select>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>Next review:
              <input
                type="date"
                value={nextReviewDate}
                onChange={(e) => setNextReviewDate(e.target.value)}
                style={{ width: "auto", height: "auto", padding: "0.25rem 0.5rem", fontSize: "0.875rem" }}
              />
              </span>
            </div>
            <div>
              <button
                type="submit"
                className="link-btn"
                disabled={submitting || !notes.trim() || !reviewer.trim()}
                style={{
                  opacity: submitting || !notes.trim() || !reviewer.trim() ? 0.5 : 1,
                }}
              >
                {submitting ? "Saving..." : "Save Review Entry"}
              </button>
            </div>
          </form>
        </article>
      )}

      {/* Review history */}
      {reviews.length > 0 && (
        <article className="panel">
          <h3>Review History</h3>
          <ul className="list">
            {reviews.map((r) => (
              <li key={r.id}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                    <strong style={{ fontSize: "0.9375rem" }}>{r.reviewer}</strong>
                    {r.cadence_type && r.cadence_type !== "ad_hoc" && (
                      <span className="badge" style={{ fontSize: "0.6875rem", textTransform: "capitalize" }}>{r.cadence_type}</span>
                    )}
                  </div>
                  <span className="small">{formatDate(r.created_at)}</span>
                </div>
                <div style={{ marginTop: "0.25rem", fontSize: "0.9375rem" }}>{r.notes}</div>
                {r.action_items && (
                  <div className="small" style={{ marginTop: "0.25rem" }}>
                    <strong>Action items:</strong> {r.action_items}
                  </div>
                )}
                {r.next_review_date && (
                  <div className="small" style={{ marginTop: "0.125rem" }}>
                    <strong>Next review:</strong>{" "}
                    {new Date(r.next_review_date + "T00:00:00").toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </div>
                )}
                {r.task_id && (
                  <div className="small" style={{ marginTop: "0.125rem", color: "var(--text-tertiary)" }}>
                    Task #{r.task_id}
                  </div>
                )}
                {r.owner_name && !r.task_id && (
                  <div className="small" style={{ marginTop: "0.125rem", color: "var(--text-tertiary)" }}>
                    Person: {r.owner_name}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </article>
      )}
    </div>
  );
}
