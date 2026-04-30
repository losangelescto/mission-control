import Link from "next/link";

import { apiClient } from "@/lib/api/client";

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

  return (
    <section className="stack">
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem" }}>
          <h1 style={{ margin: 0 }}>Suggested Tasks</h1>
          <span className="small" style={{ color: "var(--text-tertiary)" }}>
            {candidates.length} pending
          </span>
        </div>
        <p className="small" style={{ marginTop: "0.4rem", color: "var(--text-tertiary)" }}>
          Tasks the system extracted from sources you&apos;ve uploaded. Approve to convert
          into real tasks, or dismiss.
        </p>
      </div>

      {error ? (
        <article className="panel" role="alert">
          <h2>Could not load suggested tasks</h2>
          <p className="small" style={{ color: "#991b1b" }}>{error}</p>
        </article>
      ) : candidates.length === 0 ? (
        <article className="panel">
          <p className="small" style={{ color: "var(--text-tertiary)" }}>
            No suggested tasks. Upload a source to extract candidates.
          </p>
          <p className="small" style={{ marginTop: "0.4rem" }}>
            <Link href="/sources">Go to Sources →</Link>
          </p>
        </article>
      ) : (
        <ul className="list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {candidates.map((c) => (
            <CandidateRow key={c.id} candidate={c} />
          ))}
        </ul>
      )}
    </section>
  );
}
