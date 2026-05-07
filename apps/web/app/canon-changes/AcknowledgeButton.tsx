"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { apiClient } from "@/lib/api/client";

type Props = {
  eventId: number;
  alreadyReviewed: boolean;
};

export default function AcknowledgeButton({ eventId, alreadyReviewed }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (alreadyReviewed) {
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 16px",
          fontSize: 13,
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--ink-faint)",
          border: "1px solid var(--line)",
          borderRadius: 3,
          background: "var(--surface)",
        }}
      >
        Acknowledged
      </span>
    );
  }

  async function onClick() {
    setBusy(true);
    setErr(null);
    try {
      await apiClient.acknowledgeCanonChange(eventId);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to acknowledge");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 6 }}>
      <BigButton kind="primary" onClick={onClick} disabled={busy}>
        {busy ? "Acknowledging…" : "Acknowledge"}
      </BigButton>
      {err ? (
        <span style={{ fontSize: 14, color: "var(--danger)" }}>{err}</span>
      ) : null}
    </span>
  );
}
