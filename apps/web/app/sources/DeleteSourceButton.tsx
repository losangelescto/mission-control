"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiClient } from "@/lib/api/client";

type Props = {
  sourceId: number;
  sourceLabel: string;
  isActiveCanon: boolean;
};

export default function DeleteSourceButton({
  sourceId,
  sourceLabel,
  isActiveCanon,
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onClick() {
    let force = false;
    let message = `Delete "${sourceLabel}" and its chunks?\n\nThis cannot be undone.`;
    if (isActiveCanon) {
      force = window.confirm(
        `"${sourceLabel}" is the active canon version. Deleting it will leave the canonical document with NO active version.\n\nClick OK to override and delete anyway, or Cancel to keep it.`,
      );
      if (!force) return;
      message = "";
    }
    if (message && !window.confirm(message)) return;

    setBusy(true);
    setErr(null);
    try {
      await apiClient.deleteSource(sourceId, force);
      router.push("/sources");
      router.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      setErr(msg === "ACTIVE_CANON_PROTECTED" ? "Cannot delete active canon (use override)" : msg);
      setBusy(false);
    }
  }

  return (
    <span className="stack-sm">
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        title={isActiveCanon ? "Active canon — confirm will override protection" : "Delete this source"}
        style={{
          background: "transparent",
          color: "#991b1b",
          border: "1px solid #fecaca",
          padding: "0.2rem 0.5rem",
          borderRadius: "4px",
          cursor: busy ? "default" : "pointer",
          fontSize: "0.8rem",
        }}
      >
        {busy ? "…" : "Delete"}
      </button>
      {err ? (
        <span className="small" style={{ color: "#991b1b" }}>
          {err}
        </span>
      ) : null}
    </span>
  );
}
