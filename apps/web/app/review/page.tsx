import Link from "next/link";

import { BigButton } from "@/app/components/BigButton";
import { DetailSection } from "@/app/components/DetailSection";
import { PageTitle } from "@/app/components/PageTitle";
import { apiClient } from "@/lib/api/client";
import type { CadenceStatus } from "@/lib/api/types";
import { firstSearchParam } from "@/lib/search-params";

import { ReviewSessionPanel } from "./ReviewSessionPanel";

type ReviewPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function formatCadenceDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

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
    <div style={{ maxWidth: 880 }}>
      <PageTitle
        eyebrow="Daily Cadence"
        sub="A guided walk through everything that needs your attention. About ten minutes."
      >
        Review
      </PageTitle>

      {/* Entry card — pick a cadence to start a review session */}
      <article
        style={{
          background: "var(--surface-raised)",
          border: "2px solid var(--line)",
          borderRadius: 10,
          padding: "32px 36px",
          marginBottom: 28,
        }}
      >
        <div style={{ fontSize: 16, color: "var(--ink-soft)", marginBottom: 8 }}>
          {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
        </div>
        <h2
          className="serif"
          style={{
            fontFamily: "var(--serif)",
            fontSize: 28,
            fontWeight: 400,
            margin: "0 0 22px",
            color: "var(--ink)",
            letterSpacing: 0,
            textTransform: "none",
          }}
        >
          Where would you like to start?
        </h2>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {cadences.map((c, i) => (
            <CadenceChoice key={c.cadence} cadence={c} primary={i === 0} />
          ))}
          <CadenceChoice
            cadence={null}
            label="Ad Hoc"
            sub="On demand — no fixed schedule. Open a task or person to review."
            href="/review?cadence=ad_hoc#review-session"
          />
        </div>
      </article>

      {/* Rollups — what's open, grouped by why */}
      <h3
        style={{
          fontFamily: "inherit",
          fontSize: 18,
          fontWeight: 600,
          margin: "0 0 14px",
          color: "var(--ink)",
          letterSpacing: 0,
          textTransform: "none",
        }}
      >
        Rollups
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 36 }}>
        <BucketRow
          label="Urgent — high priority or due in the next 24 hours"
          count={review.urgent.length}
          tone="danger"
          href="/review?bucket=urgent#review-session"
        />
        <BucketRow
          label="Blocked — awaiting a dependency or a decision"
          count={review.blocked.length}
          tone="danger"
          href="/review?bucket=blocked#review-session"
        />
        <BucketRow
          label="Stale — no update in seven days"
          count={review.stale.length}
          href="/review?bucket=stale#review-session"
        />
        <BucketRow
          label="Due Soon — within three days"
          count={review.due_soon.length}
          href="/review?bucket=due_soon#review-session"
        />
        <BucketRow
          label="Recurring Due — recurring engine occurrences"
          count={review.recurring_due.length}
        />
        <BucketRow
          label="Candidate Review — pending suggested tasks"
          count={review.candidate_review.length}
          href="/tasks/candidates"
        />
      </div>

      {/* Open buckets — task lists, kept from the previous review queue
          so operators don't lose visibility into what's inside each rollup. */}
      <BucketDetails review={review} />

      {/* Review Session — the existing form, just wrapped in v2 spacing */}
      <article
        id="review-session"
        style={{
          marginTop: 12,
          background: "var(--surface-raised)",
          border: "2px solid var(--line)",
          borderRadius: 10,
          padding: "32px 36px",
        }}
      >
        <DetailSection title="Review Session">
          <p style={{ fontSize: 15, color: "var(--ink-soft)", margin: 0 }}>
            Select a task or person to review. Discussion notes, action items, and next review dates are preserved for the full review trail.
          </p>
        </DetailSection>
        <ReviewSessionPanel
          key={`review-panel-${initialTaskId ?? ""}-${initialOwner ?? ""}`}
          tasks={tasks}
          owners={owners}
          initialReviews={reviews}
          initialTaskId={initialTaskId}
          initialOwner={initialOwner}
        />
      </article>
    </div>
  );
}

// ─── Cadence choice (one row in the entry card) ─────────────────

function CadenceChoice({
  cadence,
  primary,
  label,
  sub,
  href,
}: {
  cadence: CadenceStatus | null;
  primary?: boolean;
  label?: string;
  sub?: string;
  href?: string;
}) {
  const text = label ?? capitalize(cadence?.cadence ?? "");
  const subText =
    sub ??
    (cadence
      ? `${cadence.window_days} day window · last ${formatCadenceDate(cadence.last_review)}${cadence.overdue ? " · overdue" : ""}`
      : "");
  const url = href ?? `/review?cadence=${cadence?.cadence ?? "daily"}#review-session`;
  const overdue = cadence?.overdue ?? false;

  return (
    <Link
      href={url}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        padding: "20px 22px",
        background: primary
          ? "color-mix(in oklch, var(--brass) 8%, var(--surface))"
          : "var(--surface)",
        border: "2px solid",
        borderColor: primary ? "var(--brass)" : "var(--line)",
        borderRadius: 8,
        color: "inherit",
        textDecoration: "none",
        transition: "border-color 120ms ease, background 120ms ease",
      }}
      className="task-list-row"
    >
      <div
        style={{
          fontSize: 19,
          fontWeight: 500,
          marginBottom: 4,
          color: "var(--ink)",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        {text}
        {overdue ? (
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--danger)",
            }}
          >
            Overdue
          </span>
        ) : null}
      </div>
      <div style={{ fontSize: 15, color: "var(--ink-soft)" }}>{subText}</div>
    </Link>
  );
}

// ─── Bucket row (rollup) ───────────────────────────────────────

function BucketRow({
  label,
  count,
  tone,
  href,
}: {
  label: string;
  count: number;
  tone?: "danger" | "default";
  href?: string;
}) {
  const isDanger = tone === "danger" && count > 0;
  const accent = isDanger ? "var(--danger)" : "var(--ink-soft)";
  const badgeBg = isDanger
    ? "color-mix(in oklch, var(--danger) 14%, transparent)"
    : "var(--canvas)";

  const inner = (
    <>
      <span
        style={{
          minWidth: 36,
          height: 36,
          padding: "0 10px",
          borderRadius: 18,
          background: badgeBg,
          color: accent,
          fontSize: 16,
          fontWeight: 600,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {count}
      </span>
      <span style={{ fontSize: 17, color: "var(--ink)" }}>{label}</span>
      <span style={{ flex: 1 }} />
      {href ? (
        <span style={{ fontSize: 14, color: "var(--ink-faint)" }}>Open →</span>
      ) : null}
    </>
  );

  const baseStyle = {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "16px 22px",
    textAlign: "left" as const,
    width: "100%",
    background: "var(--surface)",
    border: "2px solid var(--line)",
    borderRadius: 8,
    color: "inherit",
    textDecoration: "none",
    transition: "border-color 120ms ease, background 120ms ease",
  };

  if (href) {
    return (
      <Link href={href} className="task-list-row" style={baseStyle}>
        {inner}
      </Link>
    );
  }
  return <div style={baseStyle}>{inner}</div>;
}

// ─── Bucket details — keeps task-level visibility ────────────────

type DailyReview = Awaited<ReturnType<typeof apiClient.getDailyReview>>;

function BucketDetails({ review }: { review: DailyReview }) {
  const sections: { id: string; title: string; tone?: "danger"; items: typeof review.urgent }[] = [
    { id: "urgent",   title: "Urgent",   tone: "danger", items: review.urgent },
    { id: "blocked",  title: "Blocked",  tone: "danger", items: review.blocked },
    { id: "stale",    title: "Stale",    items: review.stale },
    { id: "due_soon", title: "Due Soon", items: review.due_soon },
  ];

  return (
    <div data-testid="bucket-details" style={{ marginTop: 4 }}>
      {sections.map((section) => {
        if (section.items.length === 0) return null;
        const accent = section.tone === "danger" ? "var(--danger)" : "var(--brass)";
        return (
          <section key={section.id} id={`bucket-${section.id}`} style={{ marginBottom: 28 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                paddingBottom: 12,
                marginBottom: 14,
                borderBottom: `2px solid ${accent}`,
              }}
            >
              <h2
                style={{
                  fontFamily: "inherit",
                  fontSize: 20,
                  fontWeight: 600,
                  margin: 0,
                  color: "var(--ink)",
                  letterSpacing: 0,
                  textTransform: "none",
                }}
              >
                {section.title}
              </h2>
              <span style={{ fontSize: 16, color: "var(--ink-soft)" }}>· {section.items.length}</span>
            </div>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
              {section.items.map((item) => (
                <li key={`${section.id}-${item.task_id}`}>
                  <Link
                    href={`/review?review_task=${item.task_id}#review-session`}
                    className="task-list-row"
                    style={{
                      display: "block",
                      padding: "14px 18px",
                      background: "var(--surface)",
                      border: "1px solid var(--line)",
                      borderRadius: 6,
                      textDecoration: "none",
                      color: "inherit",
                    }}
                  >
                    <div style={{ fontSize: 16, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>
                      {item.title}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                      Owner ·{" "}
                      <Link
                        href={`/review?review_owner=${item.owner_name}#review-session`}
                        style={{ textDecoration: "underline", textUnderlineOffset: 2 }}
                      >
                        {item.owner_name}
                      </Link>
                      {item.reason ? <> · {item.reason}</> : null}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {/* Recurring Due — keeps occurrence-level view since these aren't
          standard tasks (they may not even have a task_id yet). */}
      {review.recurring_due.length > 0 ? (
        <section data-testid="bucket-recurring-due" style={{ marginBottom: 28 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              paddingBottom: 12,
              marginBottom: 14,
              borderBottom: "2px solid var(--brass)",
            }}
          >
            <h2 style={{ fontFamily: "inherit", fontSize: 20, fontWeight: 600, margin: 0, color: "var(--ink)", letterSpacing: 0, textTransform: "none" }}>
              Recurring Due
            </h2>
            <span style={{ fontSize: 16, color: "var(--ink-soft)" }}>· {review.recurring_due.length}</span>
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {review.recurring_due.slice(0, 8).map((item) => (
              <li key={`recurring-${item.occurrence_id}`}>
                <div
                  style={{
                    padding: "14px 18px",
                    background: "var(--surface)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                  }}
                >
                  <div style={{ fontSize: 16, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>
                    {item.task_id ? (
                      <Link href={`/tasks?selected=${item.task_id}`}>Task #{item.task_id}</Link>
                    ) : (
                      <>Template #{item.recurrence_template_id}</>
                    )}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                    Occurrence {item.occurrence_date} · {item.status}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Candidate Review — link to the canonical Suggested page for triage */}
      {review.candidate_review.length > 0 ? (
        <section data-testid="bucket-candidate-review" style={{ marginBottom: 28 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              paddingBottom: 12,
              marginBottom: 14,
              borderBottom: "2px solid var(--brass)",
            }}
          >
            <h2 style={{ fontFamily: "inherit", fontSize: 20, fontWeight: 600, margin: 0, color: "var(--ink)", letterSpacing: 0, textTransform: "none" }}>
              Candidate Review
            </h2>
            <span style={{ fontSize: 16, color: "var(--ink-soft)" }}>· {review.candidate_review.length}</span>
            <span style={{ flex: 1 }} />
            <BigButton kind="quiet" href="/tasks/candidates">Open all →</BigButton>
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {review.candidate_review.slice(0, 8).map((item) => (
              <li key={`candidate-${item.id}`}>
                <Link
                  href="/tasks/candidates"
                  className="task-list-row"
                  style={{
                    display: "block",
                    padding: "14px 18px",
                    background: "var(--surface)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <div style={{ fontSize: 16, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>
                    {item.title}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>
                    {item.suggested_priority ? `Priority: ${item.suggested_priority} · ` : ""}
                    Source #{item.source_document_id}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function capitalize(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}
