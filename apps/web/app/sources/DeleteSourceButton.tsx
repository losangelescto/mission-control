"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/app/components/ConfirmDialog";
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
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onConfirm() {
    setBusy(true);
    setErr(null);
    try {
      // For active-canon sources we always pass force=true at this point
      // — the dialog body is the override warning, so confirming it IS
      // the override. For non-canon sources, force=false is the normal path.
      await apiClient.deleteSource(sourceId, isActiveCanon);
      router.push("/sources");
      router.refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      setErr(msg === "ACTIVE_CANON_PROTECTED" ? "Cannot delete active canon (use override)" : msg);
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <span className="stack-sm">
      <button
        type="button"
        onClick={() => setOpen(true)}
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
        data-testid="delete-source-trigger"
      >
        {busy ? "…" : "Delete"}
      </button>
      <ConfirmDialog
        isOpen={open}
        title={isActiveCanon ? "Override active canon protection?" : "Delete this source?"}
        body={
          isActiveCanon ? (
            <>
              <strong>{sourceLabel}</strong> is the active canon version.
              Deleting it will leave the canonical document with no active
              version. Confirming this will force-delete it permanently.
            </>
          ) : (
            <>
              Delete <strong>{sourceLabel}</strong> and its chunks? This cannot
              be undone.
            </>
          )
        }
        confirmLabel={isActiveCanon ? "Force delete" : "Delete"}
        cancelLabel="Cancel"
        variant="destructive"
        busy={busy}
        onConfirm={onConfirm}
        onCancel={() => setOpen(false)}
      />
      {err ? (
        <span className="small" style={{ color: "#991b1b" }}>
          {err}
        </span>
      ) : null}
    </span>
  );
}
