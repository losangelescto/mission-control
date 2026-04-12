"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function DismissCandidate({ candidateId }: { candidateId: number }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");

  async function dismiss() {
    setState("loading");
    try {
      const res = await fetch(
        `${API_BASE_URL}/task-candidates/${candidateId}/dismiss`,
        { method: "POST" }
      );
      if (res.ok) {
        setState("done");
        router.refresh();
      } else {
        setState("idle");
      }
    } catch {
      setState("idle");
    }
  }

  if (state === "done") {
    return <span className="small" style={{ color: "var(--text-tertiary)", flexShrink: 0 }}>Dismissed</span>;
  }

  return (
    <button
      onClick={dismiss}
      disabled={state === "loading"}
      style={{
        flexShrink: 0,
        padding: "0.375rem 0.75rem",
        minHeight: "auto",
        fontSize: "0.8125rem",
        background: "transparent",
        border: "1px solid var(--border-input)",
        borderRadius: "var(--radius)",
        color: "var(--text-secondary)",
        cursor: "pointer",
        fontFamily: "inherit",
        fontWeight: 600,
      }}
    >
      {state === "loading" ? "Dismissing..." : "Dismiss"}
    </button>
  );
}
