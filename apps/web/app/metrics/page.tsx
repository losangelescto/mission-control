import { BigStat } from "@/app/components/BigStat";
import { PageTitle } from "@/app/components/PageTitle";
import { apiClient } from "@/lib/api/client";
import type { StandardScore } from "@/lib/api/types";

import { ScopeSelector } from "./ScopeSelector";
import { ScoreEntry } from "./ScoreEntry";

const SEVEN_STANDARDS = [
  { name: "Anticipation",          desc: "Seeing what's needed before it's asked." },
  { name: "Recognition",           desc: "Acknowledging effort, presence, contribution." },
  { name: "Consistency",           desc: "Delivering the same standard every time." },
  { name: "Accountability",        desc: "Owning outcomes, not just tasks." },
  { name: "Emotional Intelligence", desc: "Reading the room and responding with care." },
  { name: "Ownership",             desc: "Acting like it's yours — because it is." },
  { name: "Elevation",             desc: "Raising the bar. Never settling." },
];

const FIVE_SIGNATURES = [
  { name: "The Feeling of Home",                desc: "Does this place feel like home to the people who live here?" },
  { name: "The Quality of Departure",           desc: "When someone leaves, do they leave well?" },
  { name: "The Depth of Partnership",           desc: "Are stakeholder relationships genuine and productive?" },
  { name: "The Strength of Vendor Relationships", desc: "Do vendors feel respected and aligned?" },
  { name: "The Cumulative Impression",          desc: "What is the total experience across every touchpoint?" },
];

type MetricsPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function firstParam(val: string | string[] | undefined): string | undefined {
  if (Array.isArray(val)) return val[0];
  return val;
}

export default async function MetricsPage({ searchParams }: MetricsPageProps) {
  const params = await searchParams;
  const scope = firstParam(params.scope) ?? "company";
  const scopeId = firstParam(params.scope_id) ?? "default";

  const [scores, summary, byOwner] = await Promise.all([
    apiClient.getStandardScores({ scope_type: scope, scope_id: scopeId || undefined }),
    apiClient.getMetricsSummary(),
    apiClient.getMetricsByOwner(),
  ]);

  const owners = byOwner.owners.map((o) => o.owner_name).sort();

  // Build lookup: latest score per metric_name
  const latestByName = new Map<string, StandardScore>();
  for (const s of scores) {
    const key = `${s.metric_type}:${s.metric_name}`;
    const existing = latestByName.get(key);
    if (!existing || new Date(s.created_at) > new Date(existing.created_at)) {
      latestByName.set(key, s);
    }
  }

  const overdueTone: "warn" | "default" = summary.overdue_count > 0 ? "warn" : "default";
  const blockedTone: "warn" | "default" = summary.blocked_count > 0 ? "warn" : "default";

  return (
    <div>
      <PageTitle sub="Canon as measurement. The Seven Standards and Five Emotional Signatures rated against actual operational outcomes.">
        Metrics
      </PageTitle>

      {/* Operational headline numbers — three-up on desktop, collapses on mobile */}
      <div
        className="stat-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 16,
          marginBottom: 36,
        }}
      >
        <BigStat
          label="Total tasks"
          value={summary.total_tasks}
          hint={`Average age ${summary.average_task_age_days} day${summary.average_task_age_days === 1 ? "" : "s"}`}
        />
        <BigStat
          label="Overdue"
          value={summary.overdue_count}
          tone={overdueTone}
          hint={summary.overdue_count > 0 ? "Past their due date" : "On track"}
        />
        <BigStat
          label="Currently blocked"
          value={summary.blocked_count}
          tone={blockedTone}
          hint={summary.blocked_count > 0 ? "Waiting on a dependency or decision" : "No active blockers"}
        />
      </div>

      {/* Scope selector — kept as the existing client component, framed in v2 */}
      <article
        style={{
          background: "var(--surface)",
          border: "2px solid var(--line)",
          borderRadius: 8,
          padding: "16px 22px",
          marginBottom: 32,
        }}
      >
        <ScopeSelector owners={owners} />
      </article>

      <SectionTitle>The Seven Standards</SectionTitle>
      <p
        style={{
          fontSize: 15,
          color: "var(--ink-soft)",
          margin: "0 0 18px",
          maxWidth: 640,
        }}
      >
        Co-equal standards that apply to every person. Rate 1–10.
      </p>
      {scores.filter((s) => s.metric_type === "standard").length === 0 ? (
        <p style={{ fontSize: 14, color: "var(--ink-faint)", fontStyle: "italic", marginBottom: 18 }}>
          No standards scores recorded for this scope yet. Use the sliders below to begin.
        </p>
      ) : null}
      <div className="metric-grid" style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14, marginBottom: 40 }}>
        {SEVEN_STANDARDS.map((std) => {
          const existing = latestByName.get(`standard:${std.name}`) ?? null;
          return (
            <MetricCard
              key={std.name}
              name={std.name}
              desc={std.desc}
              rating={existing?.score ?? null}
            >
              <ScoreEntry
                key={`standard:${std.name}:${scope}:${scopeId}`}
                metricType="standard"
                metricName={std.name}
                scopeType={scope}
                scopeId={scopeId || "default"}
                existing={existing}
              />
            </MetricCard>
          );
        })}
      </div>

      <SectionTitle>The Five Emotional Signatures</SectionTitle>
      <p
        style={{
          fontSize: 15,
          color: "var(--ink-soft)",
          margin: "0 0 18px",
          maxWidth: 640,
        }}
      >
        Qualitative diagnostics across every touchpoint. Rate 1–10.
      </p>
      {scores.filter((s) => s.metric_type === "signature").length === 0 ? (
        <p style={{ fontSize: 14, color: "var(--ink-faint)", fontStyle: "italic", marginBottom: 18 }}>
          No signature scores recorded for this scope yet. Use the sliders below to begin.
        </p>
      ) : null}
      <div className="metric-grid" style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14, marginBottom: 40 }}>
        {FIVE_SIGNATURES.map((sig) => {
          const existing = latestByName.get(`signature:${sig.name}`) ?? null;
          return (
            <MetricCard
              key={sig.name}
              name={sig.name}
              desc={sig.desc}
              rating={existing?.score ?? null}
            >
              <ScoreEntry
                key={`signature:${sig.name}:${scope}:${scopeId}`}
                metricType="signature"
                metricName={sig.name}
                scopeType={scope}
                scopeId={scopeId || "default"}
                existing={existing}
              />
            </MetricCard>
          );
        })}
      </div>

      <SectionTitle>By Owner</SectionTitle>
      <article
        className="table-wrap"
        style={{
          background: "var(--surface)",
          border: "2px solid var(--line)",
          borderRadius: 8,
          padding: "8px 12px",
          marginBottom: 24,
        }}
      >
        <table>
          <thead>
            <tr>
              <th>Owner</th>
              <th>Total</th>
              <th>Completed</th>
              <th>Rate</th>
              <th>Overdue</th>
              <th>Blocked</th>
            </tr>
          </thead>
          <tbody>
            {byOwner.owners.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ color: "var(--ink-faint)", fontStyle: "italic" }}>
                  No owner metrics available.
                </td>
              </tr>
            ) : (
              byOwner.owners.map((owner) => (
                <tr key={owner.owner_name}>
                  <td>{owner.owner_name}</td>
                  <td>{owner.total_tasks}</td>
                  <td>{owner.completed_tasks}</td>
                  <td>{Math.round(owner.completion_rate * 100)}%</td>
                  <td style={owner.overdue_tasks > 0 ? { color: "var(--danger)" } : undefined}>
                    {owner.overdue_tasks}
                  </td>
                  <td style={owner.blocked_tasks > 0 ? { color: "var(--danger)" } : undefined}>
                    {owner.blocked_tasks}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </article>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontFamily: "inherit",
        fontSize: 20,
        fontWeight: 600,
        margin: "0 0 6px",
        color: "var(--ink)",
        letterSpacing: 0,
        textTransform: "none",
      }}
    >
      {children}
    </h2>
  );
}

/**
 * Card per Standard / Signature: name + desc + 10-segment rating bar
 * at the top, ScoreEntry slider + textarea + Save button below.
 *
 * The 10-segment bar matches v2's StandardRow visualization (line 1026)
 * — a small, calm reflection of the saved score that doesn't require
 * its own client component to render.
 */
function MetricCard({
  name,
  desc,
  rating,
  children,
}: {
  name: string;
  desc: string;
  rating: number | null;
  children: React.ReactNode;
}) {
  return (
    <article
      style={{
        background: "var(--surface)",
        border: "2px solid var(--line)",
        borderRadius: 8,
        padding: "20px 22px",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, marginBottom: 6 }}>
        <h3
          style={{
            fontFamily: "inherit",
            fontSize: 17,
            fontWeight: 600,
            margin: 0,
            color: "var(--ink)",
            letterSpacing: 0,
            textTransform: "none",
          }}
        >
          {name}
        </h3>
        <div style={{ fontSize: 14, fontWeight: 500, color: rating ? "var(--ink)" : "var(--ink-faint)" }}>
          {rating != null ? (
            <>
              {rating} <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>/ 10</span>
            </>
          ) : (
            "—"
          )}
        </div>
      </div>
      <p style={{ fontSize: 14, color: "var(--ink-soft)", margin: "0 0 12px", lineHeight: 1.5 }}>
        {desc}
      </p>
      <div style={{ display: "flex", gap: 4, marginBottom: 14 }}>
        {[...Array(10)].map((_, i) => (
          <span
            key={i}
            aria-hidden="true"
            style={{
              flex: 1,
              height: 10,
              borderRadius: 2,
              background:
                rating != null && i < rating ? "var(--brass)" : "var(--canvas)",
              border: "1px solid var(--line)",
            }}
          />
        ))}
      </div>
      {children}
    </article>
  );
}
