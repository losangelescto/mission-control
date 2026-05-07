import { apiClient } from "@/lib/api/client";

import { BigButton } from "../components/BigButton";
import { PageTitle } from "../components/PageTitle";

import { CalloutGroup } from "./CalloutGroup";

export default async function DashboardPage() {
  const tasks = await apiClient.getTasks();

  const blocked     = tasks.filter(t => t.status === "blocked");
  const inProgress  = tasks.filter(t => t.status === "in_progress");
  const upNext      = tasks.filter(t => t.status === "up_next");

  // v2 'Calm' editorial 3-group stack (Blocked → In Progress → Up Next).
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
