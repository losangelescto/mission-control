import { apiClient } from "@/lib/api/client";
import { StandardScore } from "@/lib/api/types";
import { ScoreEntry } from "./ScoreEntry";
import { ScopeSelector } from "./ScopeSelector";

const SEVEN_STANDARDS = [
  { name: "Anticipation", desc: "Seeing what's needed before it's asked" },
  { name: "Recognition", desc: "Acknowledging effort, presence, and contribution" },
  { name: "Consistency", desc: "Delivering the same standard every time" },
  { name: "Accountability", desc: "Owning outcomes, not just tasks" },
  { name: "Emotional Intelligence", desc: "Reading the room and responding with care" },
  { name: "Ownership", desc: "Acting like it's yours — because it is" },
  { name: "Elevation", desc: "Raising the bar, never settling" },
];

const FIVE_SIGNATURES = [
  { name: "The Feeling of Home", desc: "Does this place feel like home to the people who live here?" },
  { name: "The Quality of Departure", desc: "When someone leaves, do they leave well?" },
  { name: "The Depth of Partnership", desc: "Are stakeholder relationships genuine and productive?" },
  { name: "The Strength of Vendor Relationships", desc: "Do vendors feel respected and aligned?" },
  { name: "The Cumulative Impression", desc: "What is the total experience across every touchpoint?" },
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

  return (
    <section className="stack">
      <div className="panel">
        <h1>Metrics</h1>
        <p>Seven Standards and Five Emotional Signatures</p>
      </div>

      <div className="panel">
        <ScopeSelector owners={owners} />
      </div>

      {/* Operational KPIs (kept from before) */}
      <div className="grid cols-3">
        <article className="panel">
          <h3>Total Tasks</h3>
          <p className="stat-count">{summary.total_tasks}</p>
        </article>
        <article className="panel">
          <h3>Overdue / Blocked</h3>
          <p className="stat-count">
            {summary.overdue_count} / {summary.blocked_count}
          </p>
        </article>
        <article className="panel">
          <h3>Avg Task Age (days)</h3>
          <p className="stat-count">{summary.average_task_age_days}</p>
        </article>
      </div>

      {/* Seven Standards */}
      <div className="panel">
        <h2>The Seven Standards</h2>
        <p className="small" style={{ marginBottom: "0.5rem" }}>
          Co-equal standards that apply to every person. Rate 1–10.
        </p>
        {scores.filter((s) => s.metric_type === "standard").length === 0 && (
          <p className="small" style={{ color: "var(--text-tertiary)" }}>
            No standards scores recorded for this scope yet. Use the sliders below to begin.
          </p>
        )}
      </div>
      <div className="grid cols-2">
        {SEVEN_STANDARDS.map((std) => {
          const existing = latestByName.get(`standard:${std.name}`) ?? null;
          return (
            <article key={std.name} className="panel">
              <h3>{std.name}</h3>
              <p className="small" style={{ marginBottom: "0.5rem" }}>{std.desc}</p>
              <ScoreEntry
                key={`standard:${std.name}:${scope}:${scopeId}`}
                metricType="standard"
                metricName={std.name}
                scopeType={scope}
                scopeId={scopeId || "default"}
                existing={existing}
              />
            </article>
          );
        })}
      </div>

      {/* Five Emotional Signatures */}
      <div className="panel">
        <h2>The Five Emotional Signatures</h2>
        <p className="small" style={{ marginBottom: "0.5rem" }}>
          Qualitative diagnostics across every touchpoint. Rate 1–10.
        </p>
        {scores.filter((s) => s.metric_type === "signature").length === 0 && (
          <p className="small" style={{ color: "var(--text-tertiary)" }}>
            No signature scores recorded for this scope yet. Use the sliders below to begin.
          </p>
        )}
      </div>
      <div className="grid cols-2">
        {FIVE_SIGNATURES.map((sig) => {
          const existing = latestByName.get(`signature:${sig.name}`) ?? null;
          return (
            <article key={sig.name} className="panel">
              <h3>{sig.name}</h3>
              <p className="small" style={{ marginBottom: "0.5rem" }}>{sig.desc}</p>
              <ScoreEntry
                key={`signature:${sig.name}:${scope}:${scopeId}`}
                metricType="signature"
                metricName={sig.name}
                scopeType={scope}
                scopeId={scopeId || "default"}
                existing={existing}
              />
            </article>
          );
        })}
      </div>

      {/* By Owner (kept) */}
      <article className="panel">
        <h2>By Owner</h2>
        <div className="table-wrap">
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
                  <td colSpan={6} className="small">No owner metrics available.</td>
                </tr>
              ) : (
                byOwner.owners.map((owner) => (
                  <tr key={owner.owner_name}>
                    <td>{owner.owner_name}</td>
                    <td>{owner.total_tasks}</td>
                    <td>{owner.completed_tasks}</td>
                    <td>{Math.round(owner.completion_rate * 100)}%</td>
                    <td>{owner.overdue_tasks}</td>
                    <td>{owner.blocked_tasks}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
