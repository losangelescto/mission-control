/**
 * v2 'Calm' priority flag. Renders only for high priority — medium/low get
 * nothing, leaning on the calm aesthetic where everything is "normal" unless
 * flagged. Matches /ui-update/Mission Control v2 - Calm.html line 218.
 */
export function PriorityFlag({ priority }: { priority: string | null | undefined }) {
  if (priority !== "high") return null;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        color: "var(--danger)",
        fontSize: 12,
        fontWeight: 600,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: "currentColor",
        }}
      />
      Priority
    </span>
  );
}
