import Link from "next/link";

import { apiClient } from "@/lib/api/client";
import { parsePositiveIntParam } from "@/lib/search-params";

import AcknowledgeButton from "./AcknowledgeButton";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default async function CanonChangesPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const selectedId = parsePositiveIntParam(params.event_id) ?? null;

  const list = await apiClient.getCanonChanges();
  const selected = selectedId
    ? await apiClient.getCanonChange(selectedId).catch(() => null)
    : list.events.length > 0
      ? await apiClient.getCanonChange(list.events[0].id).catch(() => null)
      : null;

  return (
    <section className="stack">
      <div className="panel">
        <h1>Canon Changes</h1>
        <p className="small">
          {list.unreviewed_count > 0
            ? `${list.unreviewed_count} unacknowledged change${list.unreviewed_count === 1 ? "" : "s"}.`
            : "All canon changes acknowledged."}
        </p>
      </div>
      <div className="grid cols-2">
        <article className="panel">
          <h2>History</h2>
          {list.events.length === 0 ? (
            <p className="small">No canon changes recorded yet.</p>
          ) : (
            <ul className="list">
              {list.events.map((event) => (
                <li key={event.id}>
                  <div>
                    <Link href={`/canon-changes?event_id=${event.id}`}>
                      <strong>{event.canon_doc_id || `event #${event.id}`}</strong>
                    </Link>{" "}
                    {event.reviewed ? null : <span className="badge">unreviewed</span>}
                  </div>
                  <div className="small">
                    {formatDate(event.created_at)} — {event.affected_task_ids.length} affected task
                    {event.affected_task_ids.length === 1 ? "" : "s"}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
        <article className="panel">
          <h2>Detail</h2>
          {selected ? (
            <div className="stack-sm">
              <div>
                <strong>{selected.canon_doc_id || `event #${selected.id}`}</strong>
              </div>
              <div className="small">
                {selected.previous_source_filename ? (
                  <>
                    {selected.previous_source_filename} → {selected.new_source_filename ?? "?"}
                  </>
                ) : (
                  <>First activated — no prior version.</>
                )}
              </div>
              <div className="small">Created {formatDate(selected.created_at)}</div>
              <div>
                <h3>Change Summary</h3>
                <p className="small">{selected.change_summary || "(none)"}</p>
              </div>
              <div>
                <h3>Impact Analysis</h3>
                <p className="small">{selected.impact_analysis || "(none)"}</p>
              </div>
              <div>
                <h3>Affected Tasks ({selected.affected_tasks.length})</h3>
                {selected.affected_tasks.length === 0 ? (
                  <p className="small">No active tasks were flagged.</p>
                ) : (
                  <ul className="list">
                    {selected.affected_tasks.map((task) => (
                      <li key={task.id}>
                        <Link href={`/tasks?task_id=${task.id}`}>{task.title}</Link>
                        <span className="small"> — owner {task.owner_name}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <AcknowledgeButton eventId={selected.id} alreadyReviewed={selected.reviewed} />
            </div>
          ) : (
            <p className="small">Select a canon change to see its detail.</p>
          )}
        </article>
      </div>
    </section>
  );
}
