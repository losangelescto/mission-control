import Link from "next/link";

import { BigButton } from "@/app/components/BigButton";
import { DetailSection } from "@/app/components/DetailSection";
import { PageTitle } from "@/app/components/PageTitle";
import { apiClient } from "@/lib/api/client";
import { parsePositiveIntParam } from "@/lib/search-params";

import AcknowledgeButton from "./AcknowledgeButton";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function formatActivatedAt(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatActivatedShort(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default async function CanonChangesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const selectedId = parsePositiveIntParam(params.event_id) ?? null;

  const list = await apiClient.getCanonChanges();
  // Mirror the auto-pick behavior the page had before — first event is the
  // pre-selected default. Users land on the most recent change, the typical
  // shape of the Canon Changes inbox (recent unreviewed at the top).
  const selected = selectedId
    ? await apiClient.getCanonChange(selectedId).catch(() => null)
    : list.events.length > 0
      ? await apiClient.getCanonChange(list.events[0].id).catch(() => null)
      : null;

  const subtitle =
    list.events.length === 0
      ? "When a canon document is updated, the change lands here for you to acknowledge."
      : list.unreviewed_count > 0
        ? `${list.unreviewed_count} unacknowledged change${list.unreviewed_count === 1 ? "" : "s"}. Acknowledge to mark as seen.`
        : "All canon changes acknowledged.";

  return (
    <div style={{ maxWidth: 880 }}>
      <PageTitle sub={subtitle}>Canon Changes</PageTitle>

      {list.events.length === 0 ? (
        <div
          style={{
            padding: "32px 28px",
            border: "2px solid var(--line)",
            borderRadius: 8,
            background: "var(--surface)",
            textAlign: "center",
            color: "var(--ink-soft)",
            fontStyle: "italic",
            fontSize: 16,
          }}
        >
          No canon changes recorded yet.
        </div>
      ) : (
        <>
          {/* History strip — single column of event-row cards */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 32 }}>
            {list.events.map((event) => {
              const isSelected = event.id === (selected?.id ?? null);
              const affected = event.affected_task_ids.length;
              return (
                <Link
                  key={event.id}
                  href={`/canon-changes?event_id=${event.id}`}
                  className="task-list-row"
                  data-selected={isSelected ? "true" : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "14px 18px",
                    background: isSelected ? "var(--surface-raised)" : "var(--surface)",
                    border: "2px solid",
                    borderColor: isSelected ? "var(--brass)" : "var(--line)",
                    borderRadius: 8,
                    textDecoration: "none",
                    color: "inherit",
                    transition: "border-color 120ms ease, background 120ms ease",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 16, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>
                      {event.canon_doc_id || `event #${event.id}`}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                      {formatActivatedShort(event.created_at)} ·{" "}
                      {affected} affected task{affected === 1 ? "" : "s"}
                    </div>
                  </div>
                  {!event.reviewed ? (
                    <span
                      style={{
                        padding: "4px 12px",
                        borderRadius: 999,
                        background: "color-mix(in oklch, var(--brass) 14%, transparent)",
                        color: "var(--brass-deep)",
                        fontSize: 11,
                        fontWeight: 600,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Unreviewed
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </div>

          {/* Selected change detail — v2 article with eyebrow + serif title */}
          {selected ? (
            <article
              style={{
                background: "var(--surface-raised)",
                border: `2px solid ${selected.reviewed ? "var(--line)" : "var(--brass)"}`,
                borderRadius: 10,
                padding: "32px 36px",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: selected.reviewed ? "var(--ink-faint)" : "var(--brass-deep)",
                  marginBottom: 12,
                }}
              >
                {selected.reviewed ? "Acknowledged" : "Unreviewed"}
              </div>

              <h2
                className="serif"
                style={{
                  fontSize: 30,
                  fontWeight: 400,
                  letterSpacing: "-0.005em",
                  lineHeight: 1.15,
                  margin: "0 0 6px",
                  color: "var(--ink)",
                }}
              >
                {selected.canon_doc_id || `Canon event #${selected.id}`}
              </h2>

              <div style={{ fontSize: 16, color: "var(--ink-soft)", marginBottom: 28 }}>
                {selected.previous_source_filename ? (
                  <>
                    <span style={{ fontFamily: "var(--font-mono)" }}>
                      {selected.previous_source_filename}
                    </span>
                    {" → "}
                    <span style={{ fontFamily: "var(--font-mono)" }}>
                      {selected.new_source_filename ?? "?"}
                    </span>
                  </>
                ) : (
                  <em>First activated — no prior version.</em>
                )}
                {" · Activated "}
                {formatActivatedAt(selected.created_at)}
              </div>

              <DetailSection title="Change Summary">
                <p style={{ fontSize: 17, lineHeight: 1.6, margin: 0, color: "var(--ink)" }}>
                  {selected.change_summary || (
                    <em style={{ color: "var(--ink-faint)" }}>No summary recorded.</em>
                  )}
                </p>
              </DetailSection>

              <DetailSection title="Impact Analysis">
                <p style={{ fontSize: 17, lineHeight: 1.6, margin: "0 0 14px", color: "var(--ink)" }}>
                  {selected.impact_analysis || (
                    <em style={{ color: "var(--ink-faint)" }}>No analysis recorded.</em>
                  )}
                </p>
                {selected.affected_tasks.length > 0 ? (
                  <>
                    <div
                      style={{
                        fontSize: 14,
                        color: "var(--ink-soft)",
                        marginBottom: 8,
                      }}
                    >
                      {selected.affected_tasks.length} task
                      {selected.affected_tasks.length === 1 ? " is" : "s are"} flagged with{" "}
                      <code>canon_update_pending</code>:
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {selected.affected_tasks.map((task) => (
                        <Link
                          key={task.id}
                          href={`/tasks?selected=${task.id}`}
                          style={{
                            display: "block",
                            padding: "12px 16px",
                            background: "var(--surface)",
                            border: "1px solid var(--line)",
                            borderRadius: 6,
                            fontSize: 15,
                            color: "var(--ink)",
                            textDecoration: "none",
                            transition: "border-color 120ms ease, background 120ms ease",
                          }}
                          className="task-list-row"
                        >
                          <div style={{ marginBottom: 2 }}>{task.title}</div>
                          <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                            owner · {task.owner_name}
                          </div>
                        </Link>
                      ))}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 15, color: "var(--ink-faint)", fontStyle: "italic" }}>
                    No active tasks were flagged.
                  </div>
                )}
              </DetailSection>

              <div style={{ marginTop: 28, display: "flex", gap: 14, flexWrap: "wrap" }}>
                <AcknowledgeButton eventId={selected.id} alreadyReviewed={selected.reviewed} />
                <BigButton kind="secondary" href={`/sources?source_id=${selected.new_source_id}`}>
                  View source document
                </BigButton>
              </div>
            </article>
          ) : null}
        </>
      )}
    </div>
  );
}
