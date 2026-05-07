import Link from "next/link";

import { apiClient } from "@/lib/api/client";

import { PageTitle } from "../../components/PageTitle";

import { CandidateRow } from "./CandidateRow";

export const dynamic = "force-dynamic";

export default async function CandidatesPage() {
  let candidates: Awaited<ReturnType<typeof apiClient.getTaskCandidates>> = [];
  let error: string | null = null;
  try {
    candidates = await apiClient.getTaskCandidates("pending_review");
  } catch (e) {
    error = e instanceof Error ? e.message : "Could not load candidates";
  }

  const subtitle =
    candidates.length === 0
      ? undefined
      : candidates.length === 1
        ? "One candidate awaiting your call. Approve to convert into a task, or dismiss."
        : `${candidates.length} candidates awaiting your call. Approve to convert into a task, or dismiss.`;

  return (
    <div>
      <PageTitle sub={subtitle ?? "Task candidates auto-extracted from your uploaded sources. Approve to convert into a task, or dismiss."}>
        Suggested
      </PageTitle>

      {error ? (
        <article
          role="alert"
          style={{
            background: "var(--surface-raised)",
            border: "2px solid var(--danger)",
            borderRadius: 8,
            padding: "20px 22px",
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18, color: "var(--danger)" }}>
            Could not load suggested tasks
          </h2>
          <p
            style={{
              marginTop: 8,
              fontSize: 15,
              color: "var(--ink-soft)",
              fontFamily: "inherit",
              letterSpacing: 0,
              textTransform: "none",
            }}
          >
            {error}
          </p>
        </article>
      ) : candidates.length === 0 ? (
        <article
          style={{
            background: "var(--surface)",
            border: "2px solid var(--line)",
            borderRadius: 8,
            padding: "32px 28px",
            textAlign: "center",
          }}
        >
          <p
            className="serif"
            style={{
              fontStyle: "italic",
              fontSize: 18,
              color: "var(--ink-soft)",
              margin: 0,
            }}
          >
            No suggested tasks. Quiet inbox today.
          </p>
          <p style={{ marginTop: 14, fontSize: 15 }}>
            <Link href="/sources" style={{ color: "var(--brass)", fontWeight: 500 }}>
              Upload a source →
            </Link>
          </p>
        </article>
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {candidates.map(c => (
            <CandidateRow key={c.id} candidate={c} />
          ))}
        </ul>
      )}
    </div>
  );
}
