"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PromptDialog } from "@/app/components/PromptDialog";
import { TimeDisplay } from "@/app/components/TimeDisplay";
import { Obstacle } from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Props = {
  taskId: number;
  initialObstacles: Obstacle[];
};

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
      <li key={o.id}>
        <details open>
          <summary>
            <span data-status="blocked" style={{ marginRight: "0.5rem" }}>
              active
            </span>
            <strong>{o.description}</strong>
          </summary>
          <div className="stack-sm" style={{ padding: "0.625rem 0.875rem" }}>
            {o.impact ? (
              <div className="small">
                <strong>Impact:</strong> {o.impact}
              </div>
            ) : null}

            {o.proposed_solutions.length > 0 ? (
              <>
                <h3 style={{ marginTop: "0.375rem" }}>Proposed solutions</h3>
                <div className="grid cols-3">
                  {o.proposed_solutions.map((s, i) => (
                    <article
                      key={`${o.id}-sol-${i}`}
                      className="panel"
                      style={{ background: "var(--bg-base)" }}
                    >
                      <div className="small" style={{ marginBottom: "0.375rem" }}>
                        <span className="badge">
                          {s.aligned_standard || "—"}
                        </span>
                        <span
                          className="small"
                          style={{
                            marginLeft: "0.375rem",
                            color: "var(--text-tertiary)",
                          }}
                        >
                          {s.source === "ai_generated" ? "AI" : "manual"}
                        </span>
                      </div>
                      <div className="small">
                        <strong>Solution:</strong> {s.solution}
                      </div>
                      {s.trade_off ? (
                        <div className="small">
                          <strong>Trade-off:</strong> {s.trade_off}
                        </div>
                      ) : null}
                      {s.first_step ? (
                        <div
                          className="small"
                          style={{ marginTop: "0.375rem" }}
                        >
                          <strong>First step:</strong> {s.first_step}
                        </div>
                      ) : null}
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <p className="small" style={{ color: "var(--text-tertiary)" }}>
                No proposed solutions yet. Click Analyze to generate three.
              </p>
            )}

            <div className="cta-row">
              <button
                type="button"
                className="link-btn"
                onClick={() => analyze(o)}
                disabled={busy !== null}
              >
                {busy === `analyze-${o.id}` ? "Analyzing..." : "Analyze"}
              </button>
              <button
                type="button"
                onClick={() => setResolving(o)}
                disabled={busy !== null}
                className="btn-secondary"
              >
                {busy === `resolve-${o.id}` ? "Resolving..." : "Resolve"}
              </button>
            </div>
          </div>
        </details>
      </li>
    );
  }

  function renderResolved(o: Obstacle) {
    return (
      <li key={o.id}>
        <details>
          <summary>
            <span data-status="completed" style={{ marginRight: "0.5rem" }}>
              resolved
            </span>
            <span style={{ color: "var(--text-tertiary)" }}>
              {o.description}
            </span>
          </summary>
          <div className="stack-sm" style={{ padding: "0.625rem 0.875rem" }}>
            {o.resolution_notes ? (
              <div className="small">
                <strong>Resolution:</strong> {o.resolution_notes}
              </div>
            ) : null}
            {o.resolved_at ? (
              <div className="small" style={{ color: "var(--text-tertiary)" }}>
                Resolved <TimeDisplay iso={o.resolved_at} format="date" />
              </div>
            ) : null}
          </div>
        </details>
      </li>
    );
  }

  return (
    <div className="stack-sm">
      <div className="meta-row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Obstacles</h3>
        <span className="small" style={{ color: "var(--text-tertiary)" }}>
          {active.length} active, {resolved.length} resolved
        </span>
      </div>

      {obstacles.length === 0 ? (
        <p className="small" style={{ color: "var(--text-tertiary)" }}>
          No obstacles recorded yet.
        </p>
      ) : (
        <ul className="list">
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
        <form onSubmit={addObstacle} className="stack-sm">
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
          <div className="cta-row">
            <button
              type="submit"
              className="link-btn"
              disabled={busy === "create" || !newDescription.trim()}
            >
              {busy === "create" ? "Saving..." : "Add Obstacle"}
            </button>
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="link-btn"
          onClick={() => setAddOpen(true)}
          disabled={busy !== null}
          style={{ alignSelf: "flex-start" }}
        >
          Add Obstacle
        </button>
      )}
    </div>
  );
}
