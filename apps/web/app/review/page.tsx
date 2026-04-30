import { apiClient } from "@/lib/api/client";
import { CadenceStatus } from "@/lib/api/types";
import { ReviewSessionPanel } from "./ReviewSessionPanel";
import Link from "next/link";
import { firstSearchParam } from "@/lib/search-params";

// Map section title → data-section slug for CSS semantic color targeting
const SECTION_SLUG: Record<string, string> = {
  "Urgent":         "urgent",
  "Blocked":        "blocked",
  "Stale":          "stale",
  "Due Soon":       "due-soon",
  "Recurring Due":  "stale",
  "Candidate Review": "due-soon",
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

function RecurringDueList({
  items,
}: {
  items: {
    occurrence_id: number;
    recurrence_template_id: number;
    task_id: number | null;
    occurrence_date: string;
    status: string;
  }[];
}) {
  return (
    <article className="panel" data-section="stale" data-testid="bucket-recurring-due">
      <h2>Recurring Due ({items.length})</h2>
      <ul className="list">
        {items.length === 0 ? (
          <li className="small">No items</li>
        ) : (
          items.slice(0, 8).map((item) => (
            <li key={`recurring-${item.occurrence_id}`}>
              <div>
                {item.task_id ? (
                  <Link
                    href={`/tasks?selected=${item.task_id}`}
                    style={{ fontWeight: 600 }}
                  >
                    Task #{item.task_id}
                  </Link>
                ) : (
                  <span style={{ fontWeight: 600 }}>
                    Template #{item.recurrence_template_id}
                  </span>
                )}
              </div>
              <div className="small">Occurrence: {item.occurrence_date}</div>
              <div className="small">Status: {item.status}</div>
            </li>
          ))
        )}
      </ul>
    </article>
  );
}

function CandidateReviewList({
  items,
}: {
  items: { id: number; title: string; suggested_priority: string | null; source_document_id: number }[];
}) {
  return (
    <article className="panel" data-section="due-soon" data-testid="bucket-candidate-review">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
        <h2>Candidate Review ({items.length})</h2>
        <Link href="/tasks/candidates" className="small">
          Open all →
        </Link>
      </div>
      <ul className="list">
        {items.length === 0 ? (
          <li className="small">No items</li>
        ) : (
          items.slice(0, 8).map((item) => (
            <li key={`candidate-${item.id}`}>
              <div>
                <Link href="/tasks/candidates" style={{ fontWeight: 600 }}>
                  {item.title}
                </Link>
              </div>
              <div className="small">
                {item.suggested_priority ? `Priority: ${item.suggested_priority} · ` : ""}
                Source #{item.source_document_id}
              </div>
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
  // Ad-hoc reviews have no schedule; show them as a fifth card alongside
  // the cadence-driven ones so the "Start Ad Hoc Review" entry point lives
  // in the same scan band as Daily / Weekly / Monthly / Quarterly.
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
      <article
        className="panel"
        style={{ borderLeft: "3px solid var(--cyan, #0891B2)" }}
        data-testid="cadence-card-ad_hoc"
      >
        <h3>Ad Hoc</h3>
        <div className="small" style={{ marginTop: "0.375rem", color: "var(--text-tertiary)" }}>
          On demand — no fixed schedule.
        </div>
        <div style={{ marginTop: "0.625rem" }}>
          <Link
            href="/review?cadence=ad_hoc#review-session"
            className="link-btn"
            style={{
              padding: "0.375rem 0.75rem",
              height: "auto",
              fontSize: "0.8125rem",
              display: "inline-block",
            }}
          >
            Start Ad Hoc Review
          </Link>
        </div>
      </article>
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
        <RecurringDueList items={review.recurring_due} />
        <CandidateReviewList items={review.candidate_review} />
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
