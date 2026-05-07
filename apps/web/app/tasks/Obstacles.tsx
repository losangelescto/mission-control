"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { PromptDialog } from "@/app/components/PromptDialog";
import { TimeDisplay } from "@/app/components/TimeDisplay";
import { Obstacle } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Props = {
  taskId: number;
  initialObstacles: Obstacle[];
};

// Small uppercase tone pill — distinct from the StatusPill primitive
// because here we want a quieter inline marker, not a dotted badge.
function ObstacleStatusPill({ resolved }: { resolved: boolean }) {
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: resolved ? "var(--success)" : "var(--danger)",
        whiteSpace: "nowrap",
      }}
    >
      {resolved ? "Resolved" : "Active"}
    </span>
  );
}

export function Obstacles({ taskId, initialObstacles }: Props) {
  const router = useRouter();
  const [obstacles, setObstacles] = useState<Obstacle[]>(initialObstacles);
  const [addOpen, setAddOpen] = useState(false);
  const [newDescription, setNewDescription] = useState("");
  const [newImpact, setNewImpact] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [resolving, setResolving] = useState<Obstacle | null>(null);

  const active = obstacles.filter((o) => o.status === "active");
  const resolved = obstacles.filter((o) => o.status === "resolved");

  async function addObstacle(e: React.FormEvent) {
    e.preventDefault();
    if (!newDescription.trim()) return;
    setBusy("create");
    try {
      const res = await fetch(`${API_BASE_URL}/tasks/${taskId}/obstacles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: newDescription.trim(),
          impact: newImpact.trim(),
          identified_by: "user",
        }),
      });
      if (res.ok) {
        const created: Obstacle = await res.json();
        setObstacles((prev) => [created, ...prev]);
        setNewDescription("");
        setNewImpact("");
        setAddOpen(false);
      }
    } finally {
      setBusy(null);
    }
  }

  async function analyze(o: Obstacle) {
    setBusy(`analyze-${o.id}`);
    try {
      const res = await fetch(`${API_BASE_URL}/obstacles/${o.id}/analyze`, {
        method: "POST",
      });
      if (res.ok) {
        const updated: Obstacle = await res.json();
        setObstacles((prev) => prev.map((x) => (x.id === o.id ? updated : x)));
      }
    } finally {
      setBusy(null);
    }
  }

  async function confirmResolve(notes: string) {
    const o = resolving;
    if (!o) return;
    setBusy(`resolve-${o.id}`);
    try {
      const res = await fetch(`${API_BASE_URL}/obstacles/${o.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution_notes: notes }),
      });
      if (res.ok) {
        const updated: Obstacle = await res.json();
        setObstacles((prev) => prev.map((x) => (x.id === o.id ? updated : x)));
        setResolving(null);
        router.refresh();
      }
    } finally {
      setBusy(null);
    }
  }

  function renderActive(o: Obstacle) {
    return (
      <li
        key={o.id}
        style={{
          background: "var(--surface)",
          border: "2px solid var(--line)",
          borderRadius: 8,
          padding: "16px 20px",
        }}
      >
        <details open>
          <summary style={{ display: "flex", alignItems: "baseline", gap: 12, listStyle: "none", cursor: "pointer" }}>
            <ObstacleStatusPill resolved={false} />
            <span style={{ flex: 1, fontSize: 16, fontWeight: 500, color: "var(--ink)" }}>
              {o.description}
            </span>
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 14, marginTop: 8, borderTop: "1px solid var(--line)" }}>
            {o.impact ? (
              <div style={{ fontSize: 14, color: "var(--ink-soft)" }}>
                <strong style={{ color: "var(--ink)" }}>Impact:</strong> {o.impact}
              </div>
            ) : null}

            {o.proposed_solutions.length > 0 ? (
              <>
                <h4
                  style={{
                    fontFamily: "inherit",
                    fontSize: 13,
                    fontWeight: 600,
                    margin: "4px 0 0",
                    color: "var(--ink-soft)",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                  }}
                >
                  Proposed solutions
                </h4>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
                  {o.proposed_solutions.map((s, i) => (
                    <article
                      key={`${o.id}-sol-${i}`}
                      style={{
                        background: "var(--surface-raised)",
                        border: "1px solid var(--line)",
                        borderRadius: 6,
                        padding: "12px 14px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            letterSpacing: "0.04em",
                            textTransform: "uppercase",
                            color: "var(--brass-deep)",
                            background: "color-mix(in oklch, var(--brass) 12%, transparent)",
                            padding: "2px 8px",
                            borderRadius: 999,
                          }}
                        >
                          {s.aligned_standard || "—"}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--ink-faint)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          {s.source === "ai_generated" ? "AI" : "Manual"}
                        </span>
                      </div>
                      <div style={{ fontSize: 14, color: "var(--ink)", marginBottom: 4 }}>
                        <strong>Solution:</strong> {s.solution}
                      </div>
                      {s.trade_off ? (
                        <div style={{ fontSize: 14, color: "var(--ink-soft)", marginBottom: 4 }}>
                          <strong>Trade-off:</strong> {s.trade_off}
                        </div>
                      ) : null}
                      {s.first_step ? (
                        <div style={{ fontSize: 14, color: "var(--ink-soft)", marginTop: 6 }}>
                          <strong>First step:</strong> {s.first_step}
                        </div>
                      ) : null}
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p style={{ fontSize: 14, color: "var(--ink-faint)", fontStyle: "italic", margin: 0 }}>
                No proposed solutions yet. Click Analyze to generate three.
              </p>
            )}

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 4 }}>
              <BigButton
                kind="secondary"
                onClick={() => analyze(o)}
                disabled={busy !== null}
              >
                {busy === `analyze-${o.id}` ? "Analyzing…" : "Analyze"}
              </BigButton>
              <BigButton
                kind="secondary"
                onClick={() => setResolving(o)}
                disabled={busy !== null}
              >
                {busy === `resolve-${o.id}` ? "Resolving…" : "Resolve"}
              </BigButton>
            </div>
          </div>
        </details>
      </li>
    );
  }

  function renderResolved(o: Obstacle) {
    return (
      <li
        key={o.id}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          padding: "12px 18px",
        }}
      >
        <details>
          <summary style={{ display: "flex", alignItems: "baseline", gap: 12, listStyle: "none", cursor: "pointer" }}>
            <ObstacleStatusPill resolved={true} />
            <span style={{ flex: 1, fontSize: 15, color: "var(--ink-soft)" }}>
              {o.description}
            </span>
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 12, marginTop: 8, borderTop: "1px solid var(--line)" }}>
            {o.resolution_notes ? (
              <div style={{ fontSize: 14, color: "var(--ink)" }}>
                <strong>Resolution:</strong> {o.resolution_notes}
              </div>
            ) : null}
            {o.resolved_at ? (
              <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>
                Resolved <TimeDisplay iso={o.resolved_at} format="date" />
              </div>
            ) : null}
          </div>
        </details>
      </li>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>
        {active.length} active · {resolved.length} resolved
      </div>

      {obstacles.length === 0 ? (
        <p style={{ fontSize: 14, color: "var(--ink-faint)", fontStyle: "italic", margin: 0 }}>
          No obstacles recorded yet.
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          {active.map(renderActive)}
          {resolved.map(renderResolved)}
        </ul>
      )}

      <PromptDialog
        isOpen={resolving !== null}
        title="Resolve obstacle"
        body={
          resolving ? (
            <>
              <div>
                <strong>Obstacle:</strong> {resolving.description}
              </div>
              {resolving.impact ? (
                <div style={{ marginTop: "0.25rem" }}>
                  <strong>Impact:</strong> {resolving.impact}
                </div>
              ) : null}
            </>
          ) : null
        }
        fieldLabel="How was this resolved?"
        fieldPlaceholder="Describe what changed and how this is no longer blocking. The recommendation engine quotes this when planning the next step."
        fieldRequired
        confirmLabel="Mark resolved"
        cancelLabel="Cancel"
        busy={resolving !== null && busy === `resolve-${resolving.id}`}
        onConfirm={confirmResolve}
        onCancel={() => setResolving(null)}
      />

      {addOpen ? (
        <form onSubmit={addObstacle} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <input
            type="text"
            placeholder="What's blocking this task?"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            autoFocus
          />
          <input
            type="text"
            placeholder="Impact (why it matters)"
            value={newImpact}
            onChange={(e) => setNewImpact(e.target.value)}
          />
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <BigButton
              kind="primary"
              type="submit"
              disabled={busy === "create" || !newDescription.trim()}
            >
              {busy === "create" ? "Saving…" : "Add obstacle"}
            </BigButton>
            <BigButton
              kind="secondary"
              onClick={() => setAddOpen(false)}
            >
              Cancel
            </BigButton>
          </div>
        </form>
      ) : (
        <div>
          <BigButton
            kind="secondary"
            onClick={() => setAddOpen(true)}
            disabled={busy !== null}
          >
            Add obstacle
          </BigButton>
        </div>
      )}
    </div>
  );
}
