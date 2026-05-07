import type { ReactNode } from "react";

type BigStatTone = "default" | "good" | "warn";

/**
 * v2 'Calm' big stat card. Editorial unit for headline numbers — small
 * label, large serif number (color reflects tone), and a one-line hint
 * underneath. Three-up grid on desktop, collapses to two-up at 560px.
 *
 * Matches /ui-update/Mission Control v2 - Calm.html line 1009.
 */
export function BigStat({
  label,
  value,
  tone = "default",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: BigStatTone;
  hint?: ReactNode;
}) {
  const valueColor =
    tone === "good" ? "var(--success)" : tone === "warn" ? "var(--danger)" : "var(--ink)";
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "2px solid var(--line)",
        borderRadius: 10,
        padding: "24px 26px",
      }}
    >
      <div style={{ fontSize: 14, color: "var(--ink-soft)", marginBottom: 12 }}>{label}</div>
      <div
        className="serif"
        style={{
          fontSize: 56,
          fontWeight: 400,
          lineHeight: 1,
          color: valueColor,
          marginBottom: hint ? 8 : 0,
          fontFeatureSettings: '"tnum" 1',
        }}
      >
        {value}
      </div>
      {hint ? (
        <div style={{ fontSize: 14, color: "var(--ink-soft)" }}>{hint}</div>
      ) : null}
    </div>
  );
}
