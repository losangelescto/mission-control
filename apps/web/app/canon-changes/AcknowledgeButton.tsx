"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
    return <span className="badge">Acknowledged</span>;
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
    <span className="stack-sm">
      <button type="button" className="link-btn" onClick={onClick} disabled={busy}>
        {busy ? "Acknowledging…" : "Acknowledge"}
      </button>
      {err ? <span className="small" style={{ color: "#991b1b" }}>{err}</span> : null}
    </span>
  );
}
