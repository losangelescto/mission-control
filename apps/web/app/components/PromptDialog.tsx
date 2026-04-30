"use client";

import { useEffect, useRef, useState } from "react";

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
  color: "var(--text-primary)",
  borderRadius: "var(--radius)",
  border: "1px solid var(--border)",
  padding: "1.25rem",
  width: "100%",
  maxWidth: "32rem",
  boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
};

// Cancel button uses the canonical .btn-secondary class from globals.css.

export type PromptDialogProps = {
  isOpen: boolean;
  title: string;
  body?: React.ReactNode;
  fieldLabel: string;
  fieldPlaceholder?: string;
  fieldRequired?: boolean;
  initialValue?: string;
  multiline?: boolean;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: (value: string) => void;
  onCancel: () => void;
};

export function PromptDialog({
  isOpen,
  title,
  body,
  fieldLabel,
  fieldPlaceholder,
  fieldRequired = false,
  initialValue = "",
  multiline = true,
  confirmLabel = "Save",
  cancelLabel = "Cancel",
  busy = false,
  onConfirm,
  onCancel,
}: PromptDialogProps) {
  const [value, setValue] = useState(initialValue);
  const [showError, setShowError] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);

  // Reset state every time the dialog re-opens so a previously typed
  // value doesn't leak across unrelated open events.
  useEffect(() => {
    if (isOpen) {
      setValue(initialValue);
      setShowError(false);
      // Focus the input on the next paint so the autofocus actually lands.
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
  }, [isOpen, initialValue]);

  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (busy) return;
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, busy, onCancel]);

  if (!isOpen) return null;

  function trySubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const trimmed = value.trim();
    if (fieldRequired && !trimmed) {
      setShowError(true);
      inputRef.current?.focus();
      return;
    }
    onConfirm(trimmed);
  }

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
        aria-labelledby="prompt-dialog-title"
        data-testid="prompt-dialog"
      >
        <h2 id="prompt-dialog-title" style={{ marginTop: 0 }}>
          {title}
        </h2>
        {body ? (
          <div className="small" style={{ color: "var(--text-tertiary)", marginBottom: "0.75rem" }}>
            {body}
          </div>
        ) : null}
        <form onSubmit={trySubmit} className="stack-sm">
          <label className="stack-sm">
            <span className="small">
              {fieldLabel}
              {fieldRequired ? <span aria-hidden="true"> *</span> : null}
            </span>
            {multiline ? (
              <textarea
                ref={inputRef as React.RefObject<HTMLTextAreaElement>}
                className="task-notes-input"
                rows={4}
                value={value}
                placeholder={fieldPlaceholder}
                onChange={(e) => {
                  setValue(e.target.value);
                  if (showError) setShowError(false);
                }}
                disabled={busy}
                required={fieldRequired}
                data-testid="prompt-input"
              />
            ) : (
              <input
                ref={inputRef as React.RefObject<HTMLInputElement>}
                type="text"
                value={value}
                placeholder={fieldPlaceholder}
                onChange={(e) => {
                  setValue(e.target.value);
                  if (showError) setShowError(false);
                }}
                disabled={busy}
                required={fieldRequired}
                data-testid="prompt-input"
              />
            )}
            {showError ? (
              <span className="small" style={{ color: "#991b1b" }} data-testid="prompt-error">
                Required
              </span>
            ) : null}
          </label>

          <div className="cta-row">
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="btn-secondary"
              data-testid="prompt-cancel"
            >
              {cancelLabel}
            </button>
            <button
              type="submit"
              className="link-btn"
              disabled={busy || (fieldRequired && !value.trim())}
              data-testid="prompt-submit"
            >
              {busy ? "Saving…" : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
