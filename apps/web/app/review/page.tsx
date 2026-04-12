import { apiClient } from "@/lib/api/client";
import { CadenceStatus } from "@/lib/api/types";
import { ReviewSessionPanel } from "./ReviewSessionPanel";
import Link from "next/link";
import { firstSearchParam } from "@/lib/search-params";

// Map section title → data-section slug for CSS semantic color targeting
const SECTION_SLUG: Record<string, string> = {
  "Urgent":   "urgent",
  "Blocked":  "blocked",
  "Stale":    "stale",
  "Due Soon": "due-soon",
};

function TaskList({
  title,
  items,
}: {
  title: string;
  items: { task_id: number; title: string; owner_name: string; reason: string }[];
}) {
  return (
    <article className="panel" data-section={SECTION_SLUG[title] ?? title.toLowerCase()}>
      <h2>{title}</h2>
      <ul className="list">
        {items.length === 0 ? (
          <li className="small">No items</li>
        ) : (
          items.map((item) => (
            <li key={`${title}-${item.task_id}`}>
              <div>
                <Link
                  href={`/review?review_task=${item.task_id}#review-session`}
                  style={{ fontWeight: 600 }}
                >
                  {item.title}
                </Link>
              </div>
              <div className="small">
                Owner:{" "}
                <Link
                  href={`/review?review_owner=${item.owner_name}#review-session`}
                  style={{ textDecoration: "underline", textUnderlineOffset: "2px" }}
                >
                  {item.owner_name}
                </Link>
              </div>
              <div className="small">Reason: {item.reason}</div>
            </li>
          ))
        )}
      </ul>
    </article>
  );
}

function formatCadenceDate(iso: string | null): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function CadenceIndicators({ cadences }: { cadences: CadenceStatus[] }) {
  return (
    <div className="grid cols-3" style={{ marginBottom: "0" }}>
      {cadences.map((c) => (
        <article
          key={c.cadence}
          className="panel"
          style={{
            borderLeft: `3px solid ${c.overdue ? "var(--red)" : "var(--green)"}`,
          }}
        >
          <h3 style={{ textTransform: "capitalize" }}>{c.cadence}</h3>
          <div style={{ marginTop: "0.375rem" }}>
            <span
              data-status={c.overdue ? "blocked" : "completed"}
              style={{ fontSize: "0.8125rem" }}
            >
              {c.overdue ? "Overdue" : "Current"}
            </span>
          </div>
          <div className="small" style={{ marginTop: "0.25rem" }}>
            Last: {formatCadenceDate(c.last_review)}
          </div>
          <div className="small">
            Window: {c.window_days} day{c.window_days !== 1 ? "s" : ""}
          </div>
        </article>
      ))}
    </div>
  );
}

type ReviewPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ReviewPage({ searchParams }: ReviewPageProps) {
  const params = await searchParams;
  const initialTaskId = firstSearchParam(params.review_task)
    ? parseInt(firstSearchParam(params.review_task)!, 10)
    : null;
  const initialOwner = firstSearchParam(params.review_owner) ?? null;

  const [review, tasks, reviews, cadences] = await Promise.all([
    apiClient.getDailyReview(),
    apiClient.getTasks(),
    apiClient.getReviews(),
    apiClient.getCadenceStatus(),
  ]);

  const owners = Array.from(new Set(tasks.map((t) => t.owner_name))).sort();

  return (
    <section className="stack">
      <div className="panel">
        <h1>Review</h1>
        <p>Review cadence, queue, and session notes</p>
      </div>

      {/* Cadence Status */}
      <CadenceIndicators cadences={cadences} />

      {/* Review Queue */}
      <div className="grid cols-2">
        <TaskList title="Urgent"   items={review.urgent}   />
        <TaskList title="Blocked"  items={review.blocked}  />
        <TaskList title="Stale"    items={review.stale}    />
        <TaskList title="Due Soon" items={review.due_soon} />
      </div>

      {/* Review Session */}
      <div className="panel" id="review-session">
        <h2>Review Session</h2>
        <p className="small" style={{ marginBottom: "0.75rem" }}>
          Select a task or person to review. Discussion notes, action items, and next review dates are preserved for the full review trail.
        </p>
      </div>
      <ReviewSessionPanel
        key={`review-panel-${initialTaskId ?? ""}-${initialOwner ?? ""}`}
        tasks={tasks}
        owners={owners}
        initialReviews={reviews}
        initialTaskId={initialTaskId}
        initialOwner={initialOwner}
      />
    </section>
  );
}
