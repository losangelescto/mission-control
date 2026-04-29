"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api/client";

const POLL_INTERVAL_MS = 60_000;

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
      className="badge"
      style={{
        marginLeft: "0.4rem",
        background: "#fee2e2",
        color: "#991b1b",
        fontSize: "0.7rem",
      }}
      aria-label={`${count} unreviewed canon changes`}
    >
      {count}
    </span>
  );
}
