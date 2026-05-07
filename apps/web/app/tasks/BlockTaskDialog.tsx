"use client";

import { useEffect, useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { apiClient } from "@/lib/api/client";
import {
  BLOCKER_TYPES,
  SEVERITIES,
  validateBlockForm,
} from "@/lib/block-flow";

type Props = {
  taskId: number;
  onClose: () => void;
  onBlocked: () => void;
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

export function BlockTaskDialog({ taskId, onClose, onBlocked }: Props) {
  const [blockerType, setBlockerType] = useState<string>(BLOCKER_TYPES[0]);
  const [blockerReason, setBlockerReason] = useState("");
  const [severity, setSeverity] = useState<string>("high");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);

  // Esc key closes the dialog.
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
    const result = validateBlockForm({
      blocker_type: blockerType,
      blocker_reason: blockerReason,
      severity,
    });
    if (!result.ok) {
      setErrors(result.errors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    try {
      await apiClient.blockTask(taskId, result.payload);
      onBlocked();
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Block failed");
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
        aria-labelledby="block-dialog-title"
        data-testid="block-task-dialog"
      >
        <h2 id="block-dialog-title" style={{ marginTop: 0 }}>
          Block Task
        </h2>
        <p className="small" style={{ color: "var(--ink-faint)" }}>
          Capture what is blocking this task so the unblock recommendation has
          the context it needs.
        </p>
        <form onSubmit={onSubmit} className="stack-sm">
          <label className="stack-sm">
            <span className="small">Blocker type</span>
            <select
              value={blockerType}
              onChange={(e) => setBlockerType(e.target.value)}
              disabled={submitting}
              data-testid="block-type"
            >
              {BLOCKER_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {errors.blocker_type ? (
              <span className="small" style={{ color: "var(--danger)" }}>
                {errors.blocker_type}
              </span>
            ) : null}
          </label>

          <label className="stack-sm">
            <span className="small">
              What is blocking this task? <span aria-hidden="true">*</span>
            </span>
            <textarea
              className="task-notes-input"
              rows={3}
              value={blockerReason}
              onChange={(e) => setBlockerReason(e.target.value)}
              disabled={submitting}
              autoFocus
              required
              data-testid="block-reason"
              placeholder="e.g. Vendor hasn't returned the signed SoW"
              maxLength={1000}
            />
            {errors.blocker_reason ? (
              <span className="small" style={{ color: "var(--danger)" }}>
                {errors.blocker_reason}
              </span>
            ) : null}
          </label>

          <label className="stack-sm">
            <span className="small">Severity</span>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              disabled={submitting}
              data-testid="block-severity"
            >
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            {errors.severity ? (
              <span className="small" style={{ color: "var(--danger)" }}>
                {errors.severity}
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
              disabled={submitting || !blockerReason.trim()}
              ariaLabel="Block this task"
            >
              <span data-testid="block-submit">
                {submitting ? "Blocking…" : "Block task"}
              </span>
            </BigButton>
            <BigButton
              kind="secondary"
              onClick={onClose}
              disabled={submitting}
              ariaLabel="Cancel block dialog"
            >
              <span data-testid="block-cancel">Cancel</span>
            </BigButton>
          </div>
        </form>
      </div>
    </div>
  );
}
