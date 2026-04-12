import { apiClient } from "@/lib/api/client";
import { KanbanBoard } from "./KanbanBoard";

export default async function DashboardPage() {
  const tasks = await apiClient.getTasks();

  return (
    <section className="stack">
      <div className="panel">
        <h1>Dashboard</h1>
        <p>Task board</p>
      </div>
      <KanbanBoard initialTasks={tasks} />
    </section>
  );
}
