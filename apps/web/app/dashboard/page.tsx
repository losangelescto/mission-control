import Link from "next/link";

import { apiClient } from "@/lib/api/client";

import { BigButton } from "../components/BigButton";
import { PageTitle } from "../components/PageTitle";

import { CalloutGroup } from "./CalloutGroup";

export default async function DashboardPage() {
  const tasks = await apiClient.getTasks();

  const blocked     = tasks.filter(t => t.status === "blocked");
  const inProgress  = tasks.filter(t => t.status === "in_progress");
  const upNext      = tasks.filter(t => t.status === "up_next");
  const backlog     = tasks.filter(t => t.status === "backlog");
  const completed   = tasks.filter(t => t.status === "completed");

  const activeOpen = blocked.length + inProgress.length + upNext.length;

  // v2 'Calm' editorial 3-group stack (Blocked → In Progress → Up Next).
  // Each group hides itself when its list is empty.
  const subtitle = buildSubtitle({
    open: activeOpen,
    blocked: blocked.length,
  });

  return (
    <div style={{ maxWidth: 880 }}>
      <PageTitle sub={subtitle}>Today</PageTitle>

      <CalloutGroup title="Blocked"     tone="danger"  tasks={blocked} />
      <CalloutGroup title="In Progress"                tasks={inProgress} />
      <CalloutGroup title="Up Next"                    tasks={upNext} />

      {/* Empty state — when no tasks are in the three active buckets the
          page would otherwise be blank. Show a single calm card with a
          create CTA, plus links to backlog / completed if either has
          tasks (so users can find the data they know exists). */}
      {activeOpen === 0 ? (
        <article
          style={{
            background: "var(--surface)",
            border: "2px solid var(--line)",
            borderRadius: 8,
            padding: "32px 28px",
            textAlign: "center",
            marginBottom: 24,
          }}
        >
          <p
            className="serif"
            style={{
              fontStyle: "italic",
              fontSize: 18,
              color: "var(--ink-soft)",
              margin: "0 0 18px",
            }}
          >
            No active tasks right now.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <BigButton kind="primary" href="/tasks/new">Create a task</BigButton>
          </div>
          {backlog.length + completed.length > 0 ? (
            <div
              style={{
                marginTop: 18,
                fontSize: 14,
                color: "var(--ink-faint)",
                display: "flex",
                gap: 16,
                justifyContent: "center",
                flexWrap: "wrap",
              }}
            >
              {backlog.length > 0 ? (
                <Link href="/tasks?status=backlog" style={{ color: "var(--brass)" }}>
                  {backlog.length} in backlog →
                </Link>
              ) : null}
              {completed.length > 0 ? (
                <Link href="/tasks?status=completed" style={{ color: "var(--brass)" }}>
                  {completed.length} completed →
                </Link>
              ) : null}
            </div>
          ) : null}
        </article>
      ) : null}

      {/* "Show Completed" only appears when there's actual completed work
          AND there's active work above it; otherwise the empty state owns
          the affordance. */}
      {activeOpen > 0 && completed.length > 0 ? (
        <div style={{ marginTop: 32 }}>
          <BigButton kind="secondary" href="/tasks?status=completed">
            Show Completed
          </BigButton>
        </div>
      ) : null}
    </div>
  );
}

function buildSubtitle({ open, blocked }: { open: number; blocked: number }): string {
  if (open === 0) return "Nothing on the active board. Backlog and completed work live in Tasks.";
  const parts: string[] = [];
  parts.push(open === 1 ? "One open thread." : `${open} open threads.`);
  if (blocked > 0) parts.push(blocked === 1 ? "One blocked." : `${blocked} blocked.`);
  return parts.join(" ");
}
