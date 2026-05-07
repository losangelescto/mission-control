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
      style={{
        fontSize: 10,
        color: "var(--brass)",
        border: "1px solid var(--brass)",
        padding: "1px 6px",
        borderRadius: 2,
        lineHeight: 1.2,
        fontWeight: 600,
        letterSpacing: "0.04em",
      }}
      aria-label={`${count} pending suggested tasks`}
    >
      {count}
    </span>
  );
}
