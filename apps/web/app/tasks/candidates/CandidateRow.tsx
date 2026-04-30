"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/app/components/ConfirmDialog";
import type { TaskCandidate } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function priorityColor(priority: string | null): string {
  switch ((priority ?? "").toLowerCase()) {
    case "high":
    case "critical":
      return "#b91c1c";
    case "medium":
      return "#92400e";
    case "low":
      return "#0369a1";
    default:
      return "var(--text-tertiary)";
  }
}

export function CandidateRow({ candidate }: { candidate: TaskCandidate }) {
  const router = useRouter();
  const [confirmOpen, setConfirmOpen] = useState<"approve" | "dismiss" | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<"approved" | "dismissed" | null>(null);

  const kind = candidate.candidate_kind ?? "candidate";
  const confidencePct =
    candidate.confidence != null ? Math.round(candidate.confidence * 100) : null;

  async function action(kind: "approve" | "dismiss") {
    setErr(null);
    setBusy(true);
    try {
      const res = await fetch(
        `${API_BASE_URL}/task-candidates/${candidate.id}/${kind}`,
        { method: "POST" },
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${kind} failed (${res.status}): ${detail}`);
      }
      setDone(kind === "approve" ? "approved" : "dismissed");
      setConfirmOpen(null);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : `${kind} failed`);
      setBusy(false);
      setConfirmOpen(null);
    }
  }

  if (done) {
    return (
      <li className="small" style={{ color: "var(--text-tertiary)" }} data-testid={`candidate-row-${candidate.id}`}>
        {done === "approved" ? "✓ Approved — added to Tasks." : "✕ Dismissed."}
      </li>
    );
  }

  return (
    <li data-testid={`candidate-row-${candidate.id}`}>
      <article
        className="panel"
        style={{
          background: "var(--bg-elevated)",
          padding: "1rem",
          marginBottom: "0.75rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-start" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: "1rem" }}>{candidate.title}</h3>
            {candidate.description ? (
              <p className="small" style={{ marginTop: "0.35rem", marginBottom: "0.5rem" }}>
                {candidate.description}
              </p>
            ) : null}
            <div className="meta-row" style={{ flexWrap: "wrap", gap: "0.4rem" }}>
              <span className="badge">{kind.replace(/_/g, " ")}</span>
              {candidate.suggested_priority ? (
                <span
                  className="badge"
                  style={{ color: priorityColor(candidate.suggested_priority) }}
                >
                  {candidate.suggested_priority}
                </span>
              ) : null}
              {candidate.canon_alignment ? (
                <span className="badge">{candidate.canon_alignment}</span>
              ) : null}
              {candidate.inferred_owner_name ? (
                <span className="small" style={{ color: "var(--text-tertiary)" }}>
                  owner: {candidate.inferred_owner_name}
                </span>
              ) : null}
              {confidencePct != null ? (
                <span className="small" style={{ color: "var(--text-tertiary)" }}>
                  confidence: {confidencePct}%
                </span>
              ) : null}
              <Link
                className="small"
                href={`/sources?source_id=${candidate.source_document_id}`}
              >
                source #{candidate.source_document_id}
              </Link>
              {candidate.source_reference ? (
                <span className="small" style={{ color: "var(--text-tertiary)" }}>
                  &ldquo;{candidate.source_reference}&rdquo;
                </span>
              ) : null}
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
            <button
              type="button"
              className="link-btn"
              onClick={() => setConfirmOpen("approve")}
              disabled={busy}
              data-testid={`candidate-approve-${candidate.id}`}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => setConfirmOpen("dismiss")}
              disabled={busy}
              className="btn-secondary"
              data-testid={`candidate-dismiss-${candidate.id}`}
            >
              Dismiss
            </button>
          </div>
        </div>
        {err ? (
          <div className="small" role="alert" style={{ color: "#991b1b", marginTop: "0.5rem" }}>
            {err}
          </div>
        ) : null}
      </article>

      <ConfirmDialog
        isOpen={confirmOpen === "approve"}
        title="Convert this candidate into a task?"
        body={
          <>
            <strong>{candidate.title}</strong> will be added to your task list with the
            suggested priority and canon alignment. You can edit it after.
          </>
        }
        confirmLabel="Approve"
        cancelLabel="Cancel"
        busy={busy}
        onConfirm={() => action("approve")}
        onCancel={() => setConfirmOpen(null)}
      />
      <ConfirmDialog
        isOpen={confirmOpen === "dismiss"}
        title="Dismiss this candidate?"
        body={
          <>
            <strong>{candidate.title}</strong> will be hidden from this list. You can
            still see it in the source it came from.
          </>
        }
        confirmLabel="Dismiss"
        cancelLabel="Cancel"
        variant="destructive"
        busy={busy}
        onConfirm={() => action("dismiss")}
        onCancel={() => setConfirmOpen(null)}
      />
    </li>
  );
}
