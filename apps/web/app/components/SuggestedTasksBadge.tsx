"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api/client";

// Mirror of CanonChangesBadge so the nav surfaces pending candidate-review
// counts at the same cadence. 10s strikes the balance between "feels live
// in the demo" and "doesn't hammer the API".
const POLL_INTERVAL_MS = 10_000;

export default function SuggestedTasksBadge() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const candidates = await apiClient.getTaskCandidates("pending_review");
        if (cancelled) return;
        setCount(candidates.length);
      } catch {
        // Silent — the link still works without a badge.
      }
    }
    load();
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (!count || count <= 0) return null;
  return (
    <span
      className="badge"
      style={{
        marginLeft: "0.4rem",
        background: "#fee2e2",
        color: "#991b1b",
        fontSize: "0.7rem",
      }}
      aria-label={`${count} pending suggested tasks`}
    >
      {count}
    </span>
  );
}
