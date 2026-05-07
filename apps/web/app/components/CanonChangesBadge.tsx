"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api/client";

// Poll every 10s so the nav reflects activation events that happened in
// other tabs / via the API within one short demo beat. The endpoint is
// cheap (small list + count) and the response is tiny, so the network
// load is negligible.
const POLL_INTERVAL_MS = 10_000;

export default function CanonChangesBadge() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const list = await apiClient.getCanonChanges(true);
        if (cancelled) return;
        setCount(list.unreviewed_count);
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
      aria-label={`${count} unreviewed canon changes`}
    >
      {count}
    </span>
  );
}
