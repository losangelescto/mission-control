import { apiClient } from "@/lib/api/client";
import { flags } from "@/lib/flags";

import { BigButton } from "../components/BigButton";
import { PageTitle } from "../components/PageTitle";

import { CalloutGroup } from "./CalloutGroup";
import { KanbanBoard } from "./KanbanBoard";

export default async function DashboardPage() {
  const tasks = await apiClient.getTasks();

  const blocked     = tasks.filter(t => t.status === "blocked");
  const inProgress  = tasks.filter(t => t.status === "in_progress");
  const upNext      = tasks.filter(t => t.status === "up_next");

  // The legacy 5-column kanban stays in code behind a build-time flag so it
  // can be opted back in via NEXT_PUBLIC_ENABLE_KANBAN=true. Default is the
  // v2 'Calm' callout-group view below.
  if (flags.kanbanDashboard) {
    return (
      <div style={{ maxWidth: 1200 }}>
        <PageTitle sub="Drag tasks between columns to change their status.">
          Dashboard
        </PageTitle>
        <KanbanBoard initialTasks={tasks} />
      </div>
    );
  }

  // v2 view: editorial 3-group stack (blocked → in progress → up next).
  // Each group hides itself when its list is empty.
  const subtitle = buildSubtitle({
    open: blocked.length + inProgress.length + upNext.length,
    blocked: blocked.length,
  });

  return (
    <div style={{ maxWidth: 880 }}>
      <PageTitle sub={subtitle}>Today</PageTitle>

      <CalloutGroup title="Blocked"     tone="danger"  tasks={blocked} />
      <CalloutGroup title="In Progress"                tasks={inProgress} />
      <CalloutGroup title="Up Next"                    tasks={upNext} />

      <div style={{ marginTop: 32 }}>
        <BigButton kind="secondary" href="/tasks?status=completed">
          Show Completed
        </BigButton>
      </div>
    </div>
  );
}

function buildSubtitle({ open, blocked }: { open: number; blocked: number }): string {
  if (open === 0) return "Nothing on the board. Quiet day.";
  const parts: string[] = [];
  parts.push(open === 1 ? "One open thread." : `${open} open threads.`);
  if (blocked > 0) parts.push(blocked === 1 ? "One blocked." : `${blocked} blocked.`);
  return parts.join(" ");
}
