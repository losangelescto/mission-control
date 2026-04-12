"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ApproveCandidate({ candidateId }: { candidateId: number }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");

  async function approve() {
    setState("loading");
    try {
      const res = await fetch(
        `${API_BASE_URL}/task-candidates/${candidateId}/approve`,
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
    return <span className="badge" style={{ flexShrink: 0 }}>Added</span>;
  }

  return (
    <button
      className="link-btn"
      onClick={approve}
      disabled={state === "loading"}
      style={{ flexShrink: 0, padding: "0.375rem 0.75rem", minHeight: "auto", fontSize: "0.8125rem" }}
    >
      {state === "loading" ? "Adding..." : "Add to Tasks"}
    </button>
  );
}
