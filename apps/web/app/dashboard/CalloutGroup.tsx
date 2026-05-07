import type { Task } from "@/lib/api/types";

import { BigTaskCard } from "../components/BigTaskCard";

/**
 * v2 'Calm' dashboard section. Renders a heading with a 2px bottom-border in
 * the section's tone color (danger for blocked, brass for everything else),
 * a count, and a stack of BigTaskCards. Returns null when the task list is
 * empty so the dashboard collapses cleanly when there's nothing to show.
 *
 * Layout matches /ui-update/Mission Control v2 - Calm.html line 488.
 */
export function CalloutGroup({
  title,
  tone = "default",
  tasks,
}: {
  title: string;
  tone?: "default" | "danger";
  tasks: Task[];
}) {
  if (tasks.length === 0) return null;
  const accent = tone === "danger" ? "var(--danger)" : "var(--brass)";
  return (
    <section style={{ marginBottom: 36 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          paddingBottom: 12,
          marginBottom: 16,
          borderBottom: `2px solid ${accent}`,
        }}
      >
        <h2
          className="group-title"
          style={{
            fontFamily: "inherit",
            fontSize: 22,
            fontWeight: 600,
            margin: 0,
            color: "var(--ink)",
            letterSpacing: 0,
            textTransform: "none",
          }}
        >
          {title}
        </h2>
        <span style={{ fontSize: 18, color: "var(--ink-soft)" }}>· {tasks.length}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {tasks.map(t => (
          <BigTaskCard key={t.id} task={t} />
        ))}
      </div>
    </section>
  );
}
