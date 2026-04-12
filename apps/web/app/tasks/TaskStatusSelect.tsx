"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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

  async function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value;
    setStatus(next);
    await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    router.refresh();
  }

  return (
    <div className="small" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <span>Status:</span>
      <select
        value={status}
        onChange={onChange}
        style={{ height: "auto", width: "auto", padding: "0.2rem 0.4rem", fontSize: "0.875rem" }}
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>
    </div>
  );
}
