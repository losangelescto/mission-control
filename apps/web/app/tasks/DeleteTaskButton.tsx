"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiClient } from "@/lib/api/client";

type Props = {
  taskId: number;
  taskTitle: string;
};

export default function DeleteTaskButton({ taskId, taskTitle }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onClick() {
    const confirmed = window.confirm(
      `Delete "${taskTitle}" and all its updates, sub-tasks, obstacles, and recommendations?\n\nThis cannot be undone.`,
    );
    if (!confirmed) return;
    setBusy(true);
    setErr(null);
    try {
      await apiClient.deleteTask(taskId);
      router.push("/tasks");
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
      setBusy(false);
    }
  }

  return (
    <span className="stack-sm">
      <button
        type="button"
        onClick={onClick}
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
      >
        {busy ? "Deleting…" : "Delete Task"}
      </button>
      {err ? (
        <span className="small" style={{ color: "#991b1b" }}>
          {err}
        </span>
      ) : null}
    </span>
  );
}
