import type { AuditEvent } from "@/lib/api/types";

const ACTION_ICON: Record<string, string> = {
  created: "✚",
  updated: "✎",
  status_changed: "↻",
  assigned: "→",
  blocked: "■",
  unblocked: "▶",
  deleted: "✕",
  completed: "✓",
  resolved: "✓",
  analyzed: "✱",
  recommendation_generated: "★",
  source_processed: "◉",
  source_failed: "!",
  uploaded: "↑",
  canon_activated: "▦",
  canon_change_detected: "△",
};

const ENTITY_LABEL: Record<string, string> = {
  task: "Task",
  sub_task: "Sub-task",
  obstacle: "Obstacle",
  source: "Source",
  review: "Review",
  canon_change: "Canon change",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function describe(event: AuditEvent): string {
  const entity = ENTITY_LABEL[event.entity_type] ?? event.entity_type;
  const action = event.action.replace(/_/g, " ");
  if (event.entity_type === "sub_task" || event.entity_type === "obstacle") {
    const title =
      (event.metadata?.title as string | undefined) ||
      (event.metadata?.description_preview as string | undefined);
    return title ? `${entity} ${action} — ${title}` : `${entity} ${action}`;
  }
  if (event.action === "status_changed") {
    const change = (event.changes?.status as { old?: string; new?: string } | undefined) ?? {};
    return `Status: ${change.old ?? "?"} → ${change.new ?? "?"}`;
  }
  if (event.entity_type === "canon_change") {
    const count = (event.metadata?.affected_task_count as number | undefined) ?? 0;
    return `Canon change detected — ${count} task${count === 1 ? "" : "s"} flagged`;
  }
  return `${entity} ${action}`;
}

type Props = {
  events: AuditEvent[];
};

export default function ActivityLog({ events }: Props) {
  if (events.length === 0) {
    return (
      <p style={{ fontSize: 14, color: "var(--ink-faint)", fontStyle: "italic", margin: 0 }}>
        No activity recorded yet.
      </p>
    );
  }
  return (
    <details>
      <summary style={{ fontSize: 14, color: "var(--ink-soft)" }}>
        Show full log · {events.length}
      </summary>
      <ul
        style={{
          listStyle: "none",
          margin: "12px 0 0",
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {events.map((event) => (
          <li
            key={event.id}
            style={{
              padding: "10px 14px",
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: 6,
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span aria-hidden="true" style={{ color: "var(--ink-faint)", flexShrink: 0 }}>
                {ACTION_ICON[event.action] ?? "·"}
              </span>
              <strong style={{ flex: 1, fontSize: 14, color: "var(--ink)" }}>
                {describe(event)}
              </strong>
              <span style={{ fontSize: 12, color: "var(--ink-faint)", flexShrink: 0 }}>
                {formatTime(event.created_at)}
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-soft)", marginLeft: 22, marginTop: 2 }}>
              by {event.actor}
              {event.changes && Object.keys(event.changes).length > 0 ? (
                <span> · {Object.keys(event.changes).join(", ")}</span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}
