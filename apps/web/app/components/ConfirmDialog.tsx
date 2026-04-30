"use client";

import { useEffect, useRef } from "react";

type Variant = "default" | "destructive";

const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
  padding: "1rem",
};

const PANEL: React.CSSProperties = {
  background: "var(--bg-base)",
  color: "var(--text)",
  borderRadius: "var(--radius)",
  border: "1px solid var(--border-subtle, #e5e7eb)",
  padding: "1.25rem",
  width: "100%",
  maxWidth: "32rem",
  boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
};

function destructiveStyle(active: boolean): React.CSSProperties {
  return {
    background: "#b91c1c",
    color: "#fff",
    border: "none",
    borderRadius: "var(--radius)",
    cursor: active ? "pointer" : "not-allowed",
    padding: "0 1rem",
    height: 44,
    fontFamily: "inherit",
    fontWeight: 600,
    width: "auto",
    opacity: active ? 1 : 0.6,
  };
}

const SECONDARY: React.CSSProperties = {
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
};

export type ConfirmDialogProps = {
  isOpen: boolean;
  title: string;
  body?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: Variant;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  isOpen,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    // Default focus to Cancel — safer than auto-focusing a destructive
    // confirm button when the dialog opens from a delete trigger.
    cancelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (busy) return;
      if (e.key === "Escape") onCancel();
      else if (e.key === "Enter" && document.activeElement?.tagName === "BUTTON")
        return; // don't auto-submit; let buttons handle their own enter
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, busy, onCancel]);

  if (!isOpen) return null;

  return (
    <div
      style={OVERLAY}
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div
        style={PANEL}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        data-testid="confirm-dialog"
      >
        <h2 id="confirm-dialog-title" style={{ marginTop: 0 }}>
          {title}
        </h2>
        {body ? (
          <div className="small" style={{ color: "var(--text-tertiary)" }}>
            {body}
          </div>
        ) : null}
        <div className="cta-row" style={{ marginTop: "1rem" }}>
          <button
            type="button"
            ref={cancelRef}
            onClick={onCancel}
            disabled={busy}
            style={SECONDARY}
            data-testid="confirm-cancel"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            style={
              variant === "destructive"
                ? destructiveStyle(!busy)
                : { ...SECONDARY, fontWeight: 700 }
            }
            data-testid="confirm-submit"
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
