import type { TaskStatus } from "@/lib/api/types";

type StatusMeta = { label: string; dot: string };

const STATUS_META: Record<TaskStatus, StatusMeta> = {
  up_next:     { label: "Up Next",     dot: "var(--brass)" },
  in_progress: { label: "In Progress", dot: "var(--success)" },
  blocked:     { label: "Blocked",     dot: "var(--danger)" },
  completed:   { label: "Completed",   dot: "var(--ink-faint)" },
  backlog:     { label: "Backlog",     dot: "var(--line-strong)" },
};

/**
 * v2 'Calm' status pill. Small uppercase letter-spaced label with a colored
 * dot whose tone reads at a glance — brass for queued, success for active,
 * danger for blocked, faint for done. Matches /ui-update/Mission Control
 * v2 - Calm.html line 194.
 */
export function StatusPill({ status }: { status: TaskStatus | string }) {
  const meta = STATUS_META[status as TaskStatus] ?? STATUS_META.up_next;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 10px",
        borderRadius: 2,
        background: "var(--surface)",
        color: "var(--ink)",
        border: "1px solid var(--line)",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: meta.dot,
          boxShadow: `0 0 0 2px color-mix(in oklch, ${meta.dot} 20%, transparent)`,
        }}
      />
      {meta.label}
    </span>
  );
}
