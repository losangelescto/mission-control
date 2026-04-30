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
  return new Date(iso).toLocaleString();
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
      <details>
        <summary>Activity Log</summary>
        <p className="small">No activity recorded yet.</p>
      </details>
    );
  }
  return (
    <details>
      <summary>Activity Log ({events.length})</summary>
      <ul className="list" style={{ marginTop: "0.5rem" }}>
        {events.map((event) => (
          <li key={event.id}>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
              <span aria-hidden="true">{ACTION_ICON[event.action] ?? "·"}</span>
              <strong style={{ flex: 1 }}>{describe(event)}</strong>
              <span className="small">{formatTime(event.created_at)}</span>
            </div>
            <div className="small" style={{ marginLeft: "1.5rem" }}>
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
