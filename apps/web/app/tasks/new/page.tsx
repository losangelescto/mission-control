import Link from "next/link";

import NewTaskForm from "./NewTaskForm";

export default function NewTaskPage() {
  return (
    <section className="stack">
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h1>New Task</h1>
          <Link href="/tasks" className="small">
            ← back to tasks
          </Link>
        </div>
      </div>
      <article className="panel">
        <NewTaskForm />
      </article>
    </section>
  );
}
