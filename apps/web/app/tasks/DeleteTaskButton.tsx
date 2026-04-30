"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/app/components/ConfirmDialog";
import { apiClient } from "@/lib/api/client";

type Props = {
  taskId: number;
  taskTitle: string;
};

export default function DeleteTaskButton({ taskId, taskTitle }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onConfirm() {
    setBusy(true);
    setErr(null);
    try {
      await apiClient.deleteTask(taskId);
      // Navigate back to /tasks WITHOUT a selected id, then refresh.
      // Going back without a selection avoids the transient panel-desync
      // where the prior detail panel renders with stale state next to a
      // freshly-fetched task list.
      router.push("/tasks");
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <span className="stack-sm">
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={busy}
        style={{
          background: "#fee2e2",
          color: "#991b1b",
          border: "1px solid #fecaca",
          padding: "0.35rem 0.6rem",
          borderRadius: "4px",
          cursor: busy ? "default" : "pointer",
          fontSize: "0.85rem",
        }}
        data-testid="delete-task-trigger"
      >
        {busy ? "Deleting…" : "Delete Task"}
      </button>
      <ConfirmDialog
        isOpen={open}
        title="Delete this task?"
        body={
          <>
            Delete <strong>{taskTitle}</strong> and all its updates, sub-tasks,
            obstacles, and recommendations? This cannot be undone.
          </>
        }
        confirmLabel="Delete Task"
        cancelLabel="Cancel"
        variant="destructive"
        busy={busy}
        onConfirm={onConfirm}
        onCancel={() => setOpen(false)}
      />
      {err ? (
        <span className="small" style={{ color: "#991b1b" }}>
          {err}
        </span>
      ) : null}
    </span>
  );
}
