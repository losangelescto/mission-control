"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { BlockTaskDialog } from "./BlockTaskDialog";
import { UnblockTaskDialog } from "./UnblockTaskDialog";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STATUSES = ["backlog", "up_next", "in_progress", "blocked", "completed"];

export function TaskStatusSelect({
  taskId,
  initialStatus,
}: {
  taskId: number;
  initialStatus: string;
}) {
  const router = useRouter();
  const [status, setStatus] = useState(initialStatus);
  // Tracked so we can revert the dropdown when the user opens the Block
  // dialog and then cancels — without a revert the dropdown would show
  // "blocked" while the task is still in its prior state.
  const previousStatus = useRef(initialStatus);
  const [blockDialogOpen, setBlockDialogOpen] = useState(false);
  const [unblockDialogOpen, setUnblockDialogOpen] = useState(false);

  async function patchStatus(next: string) {
    setStatus(next);
    previousStatus.current = next;
    await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    router.refresh();
  }

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value;
    if (next === "blocked") {
      // Open the dialog without persisting yet. The dropdown shows
      // "blocked" optimistically — we revert on Cancel via previousStatus.
      setStatus(next);
      setBlockDialogOpen(true);
      return;
    }
    if (status === "blocked") {
      // The user chose a non-blocked status while the task is blocked.
      // Funnel this through the Unblock dialog so resolution_notes are
      // captured rather than silently discarded.
      setStatus(next);
      setUnblockDialogOpen(true);
      return;
    }
    patchStatus(next);
  }

  return (
    <div className="small" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <span>Status:</span>
      <select
        value={status}
        onChange={onChange}
        style={{ height: "auto", width: "auto", padding: "0.2rem 0.4rem", fontSize: "0.875rem" }}
        data-testid="task-status-select"
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>

      {initialStatus === "blocked" ? (
        <button
          type="button"
          onClick={() => setUnblockDialogOpen(true)}
          className="link-btn"
          style={{
            padding: "0.25rem 0.6rem",
            height: "auto",
            fontSize: "0.8125rem",
            width: "auto",
          }}
          data-testid="open-unblock-dialog"
        >
          Unblock…
        </button>
      ) : null}

      {blockDialogOpen ? (
        <BlockTaskDialog
          taskId={taskId}
          onClose={() => {
            setBlockDialogOpen(false);
            setStatus(previousStatus.current);
          }}
          onBlocked={() => {
            setBlockDialogOpen(false);
            previousStatus.current = "blocked";
            router.refresh();
          }}
        />
      ) : null}

      {unblockDialogOpen ? (
        <UnblockTaskDialog
          taskId={taskId}
          onClose={() => {
            setUnblockDialogOpen(false);
            setStatus(previousStatus.current);
          }}
          onUnblocked={() => {
            setUnblockDialogOpen(false);
            router.refresh();
          }}
        />
      ) : null}
    </div>
  );
}
