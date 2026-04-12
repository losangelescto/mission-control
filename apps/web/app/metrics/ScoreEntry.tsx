"use client";

import { useState } from "react";
import { StandardScore } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ScoreEntry({
  metricType,
  metricName,
  scopeType,
  scopeId,
  existing,
}: {
  metricType: "standard" | "signature";
  metricName: string;
  scopeType: string;
  scopeId: string;
  existing: StandardScore | null;
}) {
  const [score, setScore] = useState<number>(existing?.score ?? 0);
  const [assessment, setAssessment] = useState(existing?.assessment ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await fetch(`${API_BASE_URL}/standard-scores`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope_type: scopeType,
          scope_id: scopeId,
          metric_type: metricType,
          metric_name: metricName,
          score,
          assessment: assessment.trim(),
          updated_by: "user",
        }),
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  const label =
    score === 0
      ? "Not rated"
      : score <= 3
        ? "Needs attention"
        : score <= 6
          ? "Developing"
          : "Strong";

  const color =
    score === 0
      ? "var(--text-tertiary)"
      : score <= 3
        ? "var(--red)"
        : score <= 6
          ? "var(--yellow)"
          : "var(--green)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <input
          type="range"
          min={0}
          max={10}
          value={score}
          onChange={(e) => { setScore(Number(e.target.value)); setSaved(false); }}
          style={{ flex: 1, height: "auto", padding: 0, border: "none", background: "transparent", accentColor: color }}
        />
        <span
          style={{
            fontFamily: "var(--font-mono), monospace",
            fontWeight: 700,
            fontSize: "1.25rem",
            color,
            minWidth: "2rem",
            textAlign: "right",
          }}
        >
          {score || "—"}
        </span>
      </div>
      <div className="small" style={{ color }}>{label}</div>
      <textarea
        className="task-notes-input"
        rows={2}
        placeholder="Assessment notes..."
        value={assessment}
        onChange={(e) => { setAssessment(e.target.value); setSaved(false); }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <button
          className="link-btn"
          onClick={save}
          disabled={saving}
          style={{ padding: "0.25rem 0.75rem", minHeight: "auto", fontSize: "0.8125rem" }}
        >
          {saving ? "Saving..." : "Save"}
        </button>
        {saved && <span className="small" style={{ color: "var(--green)" }}>Saved</span>}
      </div>
    </div>
  );
}
