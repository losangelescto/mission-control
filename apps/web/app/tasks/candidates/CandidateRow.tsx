"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { ConfirmDialog } from "@/app/components/ConfirmDialog";
import type { TaskCandidate } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Priority chip color, kept here because v2 doesn't have a per-priority
// token — these are intentionally one-off accents that read as muted on
// a candidate row, not as the strong status signal a Task gets.
function priorityColor(priority: string | null): string {
  switch ((priority ?? "").toLowerCase()) {
    case "high":
    case "critical":
      return "var(--danger)";
    case "medium":
      return "var(--warning)";
    case "low":
      return "var(--success)";
    default:
      return "var(--ink-faint)";
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

  async function action(action: "approve" | "dismiss") {
    setErr(null);
    setBusy(true);
    try {
      const res = await fetch(
        `${API_BASE_URL}/task-candidates/${candidate.id}/${action}`,
        { method: "POST" },
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${action} failed (${res.status}): ${detail}`);
      }
      setDone(action === "approve" ? "approved" : "dismissed");
      setConfirmOpen(null);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : `${action} failed`);
      setBusy(false);
      setConfirmOpen(null);
    }
  }

  if (done) {
    return (
      <li
        data-testid={`candidate-row-${candidate.id}`}
        style={{
          padding: "14px 22px",
          background: "var(--surface)",
          border: "2px solid var(--line)",
          borderRadius: 8,
          fontSize: 15,
          color: "var(--ink-faint)",
          fontStyle: "italic",
        }}
      >
        {done === "approved"
          ? `Approved · ${candidate.title} added to Tasks.`
          : `Dismissed · ${candidate.title}.`}
      </li>
    );
  }

  return (
    <li data-testid={`candidate-row-${candidate.id}`} style={{ listStyle: "none" }}>
      <article
        style={{
          background: "var(--surface)",
          border: "2px solid var(--line)",
          borderRadius: 8,
          padding: "24px 26px",
        }}
      >
        <div
          style={{
            fontSize: 19,
            fontWeight: 500,
            lineHeight: 1.35,
            marginBottom: 10,
            color: "var(--ink)",
          }}
        >
          {candidate.title}
        </div>

        {candidate.description ? (
          <p
            style={{
              fontSize: 15,
              lineHeight: 1.55,
              color: "var(--ink-soft)",
              margin: "0 0 14px",
            }}
          >
            {candidate.description}
          </p>
        ) : null}

        {/* Source attribution — primary citation, mirrors v2's "From your
            call with the building engineer · Monday" pattern. */}
        <div style={{ fontSize: 14, color: "var(--ink-soft)", marginBottom: 14 }}>
          From{" "}
          <Link
            href={`/sources?source_id=${candidate.source_document_id}`}
            style={{ color: "var(--brass)", textDecoration: "underline", textDecorationColor: "color-mix(in oklch, var(--brass) 35%, transparent)" }}
          >
            source #{candidate.source_document_id}
          </Link>
          {candidate.source_reference ? (
            <>
              {" "}· <em>&ldquo;{candidate.source_reference}&rdquo;</em>
            </>
          ) : null}
        </div>

        {/* Secondary metadata row — kept from the previous version for
            triage value (kind, priority, canon, owner, confidence). v2
            doesn't show this; we keep it because operators rely on it
            to decide approve vs dismiss. */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 14,
            fontSize: 12,
            color: "var(--ink-faint)",
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            marginBottom: 18,
          }}
        >
          <span>{kind.replace(/_/g, " ")}</span>
          {candidate.suggested_priority ? (
            <span style={{ color: priorityColor(candidate.suggested_priority) }}>
              {candidate.suggested_priority}
            </span>
          ) : null}
          {candidate.canon_alignment ? <span>{candidate.canon_alignment}</span> : null}
          {candidate.inferred_owner_name ? (
            <span>owner · {candidate.inferred_owner_name}</span>
          ) : null}
          {confidencePct != null ? <span>{confidencePct}%</span> : null}
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <BigButton
            kind="primary"
            onClick={() => setConfirmOpen("approve")}
            disabled={busy}
            ariaLabel={`Approve candidate: ${candidate.title}`}
          >
            <span data-testid={`candidate-approve-${candidate.id}`}>Approve</span>
          </BigButton>
          <BigButton
            kind="secondary"
            onClick={() => setConfirmOpen("dismiss")}
            disabled={busy}
            ariaLabel={`Dismiss candidate: ${candidate.title}`}
          >
            <span data-testid={`candidate-dismiss-${candidate.id}`}>Dismiss</span>
          </BigButton>
        </div>

        {err ? (
          <div
            role="alert"
            style={{
              marginTop: 14,
              fontSize: 14,
              color: "var(--danger)",
            }}
          >
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
