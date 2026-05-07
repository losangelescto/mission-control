import { apiClient } from "@/lib/api/client";

import { BigButton } from "../components/BigButton";
import { PageTitle } from "../components/PageTitle";

import { KanbanBoard } from "./KanbanBoard";

export default async function DashboardPage() {
  const tasks = await apiClient.getTasks();

  // Subtitle reflects only the "active" flow (blocked + in_progress +
  // up_next) since those are the buckets users come to /dashboard to act
  // on. Completed and backlog count toward the kanban-vs-empty-state
  // decision below, but not the editorial subtitle copy.
  const blocked = tasks.filter(t => t.status === "blocked").length;
  const activeOpen =
    tasks.filter(t => t.status === "blocked").length +
    tasks.filter(t => t.status === "in_progress").length +
    tasks.filter(t => t.status === "up_next").length;
  const subtitle = buildSubtitle({ open: activeOpen, blocked });

  // Empty state owns the page only when there are zero tasks across all
  // five statuses. If anything exists in any column the kanban renders;
  // empty columns just render the "No tasks" italic placeholder.
  if (tasks.length === 0) {
    return (
      <div>
        <PageTitle sub="Quiet day. Create a task to get started.">Today</PageTitle>
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
            No tasks yet.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <BigButton kind="primary" href="/tasks/new">Create a task</BigButton>
          </div>
        </article>
      </div>
    );
  }

  return (
    <div>
      <PageTitle sub={subtitle}>Today</PageTitle>
      <KanbanBoard initialTasks={tasks} />
    </div>
  );
}

function buildSubtitle({ open, blocked }: { open: number; blocked: number }): string {
  if (open === 0) return "Nothing active. Drag a backlog card up to get started.";
  const parts: string[] = [];
  parts.push(open === 1 ? "One open thread." : `${open} open threads.`);
  if (blocked > 0) parts.push(blocked === 1 ? "One blocked." : `${blocked} blocked.`);
  return parts.join(" ");
}
