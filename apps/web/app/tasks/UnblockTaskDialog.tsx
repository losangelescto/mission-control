"use client";

import { useEffect, useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { apiClient } from "@/lib/api/client";
import {
  UNBLOCK_NEXT_STATUSES,
  validateUnblockForm,
} from "@/lib/block-flow";
import type { TaskStatus } from "@/lib/api/types";

type Props = {
  taskId: number;
  onClose: () => void;
  onUnblocked: () => void;
};

const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(15, 13, 10, 0.4)",
  backdropFilter: "blur(2px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
  padding: "1rem",
};

const PANEL: React.CSSProperties = {
  background: "var(--surface-raised)",
  color: "var(--ink)",
  borderRadius: 10,
  border: "2px solid var(--line)",
  padding: "28px 30px",
  width: "100%",
  maxWidth: "32rem",
  boxShadow: "var(--shadow-md)",
};

export function UnblockTaskDialog({ taskId, onClose, onUnblocked }: Props) {
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [nextStatus, setNextStatus] = useState<string>("in_progress");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);
    const result = validateUnblockForm({
      resolution_notes: resolutionNotes,
      next_status: nextStatus,
    });
    if (!result.ok) {
      setErrors(result.errors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    try {
      await apiClient.unblockTask(taskId, {
        resolution_notes: result.payload.resolution_notes,
        next_status: result.payload.next_status as TaskStatus,
      });
      onUnblocked();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Unblock failed");
      setSubmitting(false);
    }
  }

  return (
    <div
      style={OVERLAY}
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
      role="presentation"
    >
      <div
        style={PANEL}
        role="dialog"
        aria-modal="true"
        aria-labelledby="unblock-dialog-title"
        data-testid="unblock-task-dialog"
      >
        <h2 id="unblock-dialog-title" style={{ marginTop: 0 }}>
          Unblock Task
        </h2>
        <p className="small" style={{ color: "var(--ink-faint)" }}>
          The resolution notes feed the next recommendation prompt — a clear
          note here lets the LLM build on what you just resolved instead of
          re-suggesting it.
        </p>
        <form onSubmit={onSubmit} className="stack-sm">
          <label className="stack-sm">
            <span className="small">Resolution notes</span>
            <textarea
              className="task-notes-input"
              rows={3}
              value={resolutionNotes}
              onChange={(e) => setResolutionNotes(e.target.value)}
              disabled={submitting}
              autoFocus
              data-testid="unblock-notes"
              placeholder="What changed? How was the blocker resolved?"
            />
          </label>

          <label className="stack-sm">
            <span className="small">Next status</span>
            <select
              value={nextStatus}
              onChange={(e) => setNextStatus(e.target.value)}
              disabled={submitting}
              data-testid="unblock-next-status"
            >
              {UNBLOCK_NEXT_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {errors.next_status ? (
              <span className="small" style={{ color: "var(--danger)" }}>
                {errors.next_status}
              </span>
            ) : null}
          </label>

          {serverError ? (
            <p className="small" style={{ color: "var(--danger)" }}>
              {serverError}
            </p>
          ) : null}

          <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
            <BigButton
              kind="primary"
              type="submit"
              disabled={submitting}
              ariaLabel="Unblock this task"
            >
              <span data-testid="unblock-submit">
                {submitting ? "Unblocking…" : "Unblock task"}
              </span>
            </BigButton>
            <BigButton
              kind="secondary"
              onClick={onClose}
              disabled={submitting}
              ariaLabel="Cancel unblock dialog"
            >
              <span data-testid="unblock-cancel">Cancel</span>
            </BigButton>
          </div>
        </form>
      </div>
    </div>
  );
}
