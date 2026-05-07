import Link from "next/link";

import { BigButton } from "@/app/components/BigButton";
import { CloseDetailPanel } from "@/app/components/CloseDetailPanel";
import { DetailSection } from "@/app/components/DetailSection";
import { PageTitle } from "@/app/components/PageTitle";
import { PriorityFlag } from "@/app/components/PriorityFlag";
import { Recommendation } from "@/app/components/Recommendation";
import { StatusPill } from "@/app/components/StatusPill";
import { apiClient, TaskFilters } from "@/lib/api/client";
import { flags } from "@/lib/flags";
import { firstSearchParam, parsePositiveIntParam } from "@/lib/search-params";
import { formatTaskDue } from "@/lib/time-display";

import ActivityLog from "./ActivityLog";
import { ApproveCandidate } from "./ApproveCandidate";
import DeleteTaskButton from "./DeleteTaskButton";
import { DismissCandidate } from "./DismissCandidate";
import GenerateRecommendationButton from "./GenerateRecommendationButton";
import { Obstacles } from "./Obstacles";
import { SubTasks } from "./SubTasks";
import { TaskNotes } from "./TaskNotes";
import { TasksFiltersForm } from "./TasksFiltersForm";
import { TaskStatusSelect } from "./TaskStatusSelect";
import { TaskUpdateInput } from "./TaskUpdateInput";

type TasksPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function TasksPage({ searchParams }: TasksPageProps) {
  const params = await searchParams;
  const filters: TaskFilters = {
    status: (firstSearchParam(params.status) as TaskFilters["status"]) || undefined,
    owner_name: firstSearchParam(params.owner_name),
    priority: firstSearchParam(params.priority),
    due_before: firstSearchParam(params.due_before),
  };

  const fallbackFilterOptions = {
    statuses: ["backlog", "up_next", "in_progress", "blocked", "completed"],
    priorities: ["low", "medium", "high", "critical"],
    owners: [] as string[],
  };
  const filterOptions = await apiClient.getTaskFilterOptions().catch(
    () => fallbackFilterOptions
  );

  const withExtraOption = (opts: string[], extra: string | undefined) => {
    if (!extra?.trim()) return opts;
    if (opts.includes(extra)) return opts;
    return [...opts, extra].sort((a, b) => a.localeCompare(b));
  };
  const statusOptionsForSelect = withExtraOption(
    filterOptions.statuses,
    firstSearchParam(params.status)
  );
  const priorityOptionsForSelect = withExtraOption(
    filterOptions.priorities,
    firstSearchParam(params.priority)
  );
  const ownerOptionsForSelect = (() => {
    const set = new Set(filterOptions.owners);
    const owner = firstSearchParam(params.owner_name);
    if (owner) set.add(owner);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  })();

  let tasks: Awaited<ReturnType<typeof apiClient.getTasks>> = [];
  let tasksError: string | null = null;
  try {
    tasks = await apiClient.getTasks(filters);
  } catch (e) {
    tasksError =
      e instanceof Error
        ? e.message
        : "Could not load tasks. Is the API running (see NEXT_PUBLIC_API_URL)?";
  }

  // Only honour an explicit ?selected= in the URL. Auto-picking tasks[0]
  // caused stale detail panels after deletes (see git history).
  const selectedId = parsePositiveIntParam(params.selected);
  const selectedTask = selectedId
    ? await apiClient.getTask(selectedId).catch(() => null)
    : null;
  const updates = selectedTask
    ? await apiClient.getTaskUpdates(selectedTask.id).catch(() => [])
    : [];

  const daily = await apiClient.getDailyReview().catch(() => null);
  const recurringForTask =
    daily && selectedTask
      ? daily.recurring_due.filter((item) => item.task_id === selectedTask.id)
      : [];
  const blockedSet = new Set(daily?.blocked.map((item) => item.task_id) ?? []);

  // Always read the latest persisted recommendation server-side; the
  // GenerateRecommendationButton client component triggers fresh LLM
  // calls and router.refresh()'s the page so the new rec lands here on
  // the next render. The page never blocks on the LLM during SSR.
  let recommendation: Awaited<ReturnType<typeof apiClient.generateRecommendation>> | null = null;
  if (selectedTask) {
    recommendation = await apiClient
      .getLatestRecommendation(selectedTask.id)
      .catch(() => null);
  }

  const recommendationHistory = selectedTask
    ? await apiClient.listTaskRecommendations(selectedTask.id).catch(() => [])
    : [];

  const subTasks = selectedTask
    ? await apiClient.listSubTasks(selectedTask.id).catch(() => [])
    : [];
  const obstacles = selectedTask
    ? await apiClient.listObstacles(selectedTask.id).catch(() => [])
    : [];

  const auditEvents = selectedTask
    ? await apiClient
        .getTaskAuditLog(selectedTask.id)
        .then((r) => r.events)
        .catch(() => [])
    : [];

  const candidates = await apiClient.getTaskCandidates("pending_review").catch(() => []);

  // Build query string to preserve current filters when selecting a task.
  const filterQuery = new URLSearchParams();
  if (filters.status) filterQuery.set("status", filters.status);
  if (filters.owner_name) filterQuery.set("owner_name", filters.owner_name);
  if (filters.priority) filterQuery.set("priority", filters.priority);
  if (filters.due_before) filterQuery.set("due_before", filters.due_before);
  const filterPrefix = filterQuery.toString();

  // The closeHref keeps current filters but drops `selected=`. Used by both
  // the row-toggle behavior (clicking the selected row deselects it) and
  // the X / Escape close affordances on the task-detail article.
  const closeDetailHref = filterPrefix ? `/tasks?${filterPrefix}` : "/tasks";

  function taskHref(taskId: number, isCurrentlySelected: boolean): string {
    if (isCurrentlySelected) return closeDetailHref;
    const parts = filterPrefix ? `${filterPrefix}&selected=${taskId}` : `selected=${taskId}`;
    return `/tasks?${parts}`;
  }

  const subtitle =
    tasks.length === 0
      ? "Every task you own. Filter by status, owner, priority, or due date."
      : tasks.length === 1
        ? "One task on the list."
        : `${tasks.length} on the list. Filter to narrow down, click a row to see the detail.`;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 24,
          flexWrap: "wrap",
          marginBottom: 16,
        }}
      >
        <PageTitle sub={subtitle}>Tasks</PageTitle>
        <BigButton kind="primary" href="/tasks/new">+ New Task</BigButton>
      </div>

      {/* Filters — kept as a v2 card with the existing client form inside */}
      <article
        className="filter-row"
        style={{
          background: "var(--surface)",
          border: "2px solid var(--line)",
          borderRadius: 8,
          padding: "20px 22px",
          marginBottom: 24,
        }}
      >
        <TasksFiltersForm
          statusOptions={statusOptionsForSelect}
          priorityOptions={priorityOptionsForSelect}
          ownerOptions={ownerOptionsForSelect}
          initialStatus={firstSearchParam(params.status) ?? ""}
          initialOwner={firstSearchParam(params.owner_name) ?? ""}
          initialPriority={firstSearchParam(params.priority) ?? ""}
          initialDueBeforeIso={firstSearchParam(params.due_before)}
        />
      </article>

      {tasksError ? (
        <article
          role="alert"
          style={{
            background: "var(--surface-raised)",
            border: "2px solid var(--danger)",
            borderRadius: 8,
            padding: "20px 22px",
            marginBottom: 24,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18, color: "var(--danger)", fontFamily: "inherit", letterSpacing: 0, textTransform: "none" }}>
            Could not load tasks
          </h2>
          <p style={{ marginTop: 8, fontSize: 15, color: "var(--ink-soft)" }}>{tasksError}</p>
          <p style={{ marginTop: 4, fontSize: 14, color: "var(--ink-faint)" }}>
            Start the API (for example <code>uvicorn app.main:app --reload --port 8000</code>{" "}
            from <code>apps/api</code>) and ensure <code>NEXT_PUBLIC_API_URL</code> in{" "}
            <code>apps/web/.env.local</code> matches.
          </p>
        </article>
      ) : null}

      {/* Task list — v2 single column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 40 }}>
        {tasks.length === 0 && !tasksError ? (
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
            No tasks match these filters.
          </div>
        ) : (
          tasks.map((task) => {
            const due = formatTaskDue(task.due_at);
            const isSelected = task.id === selectedId;
            return (
              <Link
                key={task.id}
                href={taskHref(task.id, isSelected)}
                className="task-list-row"
                data-selected={isSelected ? "true" : undefined}
                aria-pressed={isSelected}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  padding: "18px 22px",
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
                  <div
                    style={{
                      fontSize: 18,
                      fontWeight: 500,
                      lineHeight: 1.35,
                      marginBottom: 8,
                      color: "var(--ink)",
                    }}
                  >
                    {task.title}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      alignItems: "center",
                      gap: 12,
                      fontSize: 14,
                      color: "var(--ink-soft)",
                    }}
                  >
                    <PriorityFlag priority={task.priority} />
                    <span>{task.owner_name}</span>
                    <span aria-hidden="true" style={{ color: "var(--ink-faint)" }}>·</span>
                    <span style={{ color: due.overdue ? "var(--danger)" : "var(--ink-soft)" }}>
                      {due.overdue ? "Overdue · " : "Due "}
                      {due.text}
                    </span>
                  </div>
                </div>
                <StatusPill status={task.status} />
              </Link>
            );
          })
        )}
      </div>

      {/* Selected task detail */}
      {selectedTask ? (
        <article
          className="task-detail"
          style={{
            background: "var(--surface-raised)",
            border: "2px solid var(--line)",
            borderRadius: 10,
            padding: "32px 36px",
            marginBottom: 32,
            position: "relative",
          }}
        >
          <CloseDetailPanel closeHref={closeDetailHref} />

          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 18, flexWrap: "wrap" }}>
            <StatusPill status={selectedTask.status} />
            <PriorityFlag priority={selectedTask.priority} />
            {blockedSet.has(selectedTask.id) ? (
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--danger)",
                }}
              >
                Blocker active
              </span>
            ) : null}
          </div>

          <h2
            className="serif"
            style={{
              fontSize: 32,
              fontWeight: 400,
              letterSpacing: "-0.005em",
              lineHeight: 1.15,
              margin: "0 0 8px",
              color: "var(--ink)",
            }}
          >
            {selectedTask.title}
          </h2>

          <div style={{ fontSize: 16, color: "var(--ink-soft)", marginBottom: 28 }}>
            Owned by <strong style={{ color: "var(--ink)" }}>{selectedTask.owner_name}</strong>
            {" · "}
            {(() => {
              const due = formatTaskDue(selectedTask.due_at);
              return (
                <span style={{ color: due.overdue ? "var(--danger)" : "var(--ink-soft)" }}>
                  {due.overdue ? "Overdue · " : "Due "}
                  {due.text}
                </span>
              );
            })()}
            {recurringForTask.length > 0 ? (
              <>
                {" · "}
                <span>{recurringForTask.length} recurring occurrence{recurringForTask.length === 1 ? "" : "s"}</span>
              </>
            ) : null}
          </div>

          <DetailSection title="Change status">
            <TaskStatusSelect taskId={selectedTask.id} initialStatus={selectedTask.status} />
          </DetailSection>

          <DetailSection title="Description">
            <TaskNotes
              taskId={selectedTask.id}
              initialDescription={selectedTask.description}
              updatedAt={selectedTask.updated_at}
            />
          </DetailSection>

          <DetailSection title="Steps">
            <SubTasks taskId={selectedTask.id} initialSubTasks={subTasks} />
          </DetailSection>

          <DetailSection title="Obstacles">
            <Obstacles taskId={selectedTask.id} initialObstacles={obstacles} />
          </DetailSection>

          <DetailSection title="What I think you should do next">
            <Recommendation>
              <GenerateRecommendationButton
                taskId={selectedTask.id}
                label={
                  recommendation && recommendation.recommendation_type === "unblock"
                    ? "Regenerate Analysis"
                    : undefined
                }
              />
              {recommendation && recommendation.recommendation_type === "unblock" && recommendation.unblock_analysis ? (
                <UnblockAnalysisView rec={recommendation} />
              ) : recommendation ? (
                <RecommendationView rec={recommendation} />
              ) : (
                <p style={{ marginTop: 14, fontSize: 15, color: "var(--ink-soft)", fontStyle: "italic" }}>
                  Generate to view the latest recommendation.
                </p>
              )}
            </Recommendation>
          </DetailSection>

          {recommendationHistory.length > 0 ? (
            <DetailSection title={`Previous recommendations · ${recommendationHistory.length}`}>
              <details style={{ marginTop: 0 }}>
                <summary>Show history</summary>
                <ul className="list" style={{ marginTop: "0.5rem" }}>
                  {recommendationHistory.slice(0, 5).map((h) => (
                    <li key={h.id}>
                      <div className="meta-row">
                        <span className="badge" data-status={h.recommendation_type === "unblock" ? "blocked" : "up_next"}>
                          {h.recommendation_type}
                        </span>
                        <span>
                          {new Date(h.created_at).toLocaleString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <div className="small" style={{ marginTop: "0.25rem" }}>
                        <strong>Standard:</strong> {h.standard}
                      </div>
                      <div className="small">
                        <strong>Next action:</strong> {h.next_action}
                      </div>
                    </li>
                  ))}
                </ul>
              </details>
            </DetailSection>
          ) : null}

          <DetailSection title="Activity">
            <ActivityLog events={auditEvents} />
          </DetailSection>

          <DetailSection title="Updates">
            <TaskUpdateInput taskId={selectedTask.id} initialUpdates={[...updates].reverse()} />
          </DetailSection>

          <DetailSection title="Danger zone">
            <DeleteTaskButton taskId={selectedTask.id} taskTitle={selectedTask.title} />
          </DetailSection>
        </article>
      ) : null}

      {/* Inline candidates duplicate — flag-gated. Default off because
          /tasks/candidates is the canonical Suggested page after PR #5. */}
      {flags.inlineCandidatesOnTasks ? (
        <InlineCandidatesPanel
          candidates={candidates}
          showAll={firstSearchParam(params.show_all_candidates) === "1"}
          filters={filters}
        />
      ) : null}
    </div>
  );
}

// ─── Recommendation views ───────────────────────────────────────────

type Rec = NonNullable<Awaited<ReturnType<typeof apiClient.generateRecommendation>>>;

function RecommendationView({ rec }: { rec: Rec }) {
  return (
    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 16 }}>
        <strong style={{ color: "var(--ink)" }}>Objective:</strong>{" "}
        <span style={{ color: "var(--ink-soft)" }}>{rec.objective}</span>
      </div>
      <div style={{ fontSize: 14, color: "var(--ink-faint)" }}>
        <strong>Standard:</strong> {rec.standard}
      </div>
      <div style={{ fontSize: 15, lineHeight: 1.55, color: "var(--ink)" }}>{rec.first_principles_plan}</div>
      {rec.viable_options.length > 0 ? (
        <ul style={{ paddingLeft: "1.25rem", color: "var(--ink-soft)", fontSize: 15 }}>
          {rec.viable_options.map((option) => (
            <li key={option}>{option}</li>
          ))}
        </ul>
      ) : null}
      <div style={{ fontSize: 16 }}>
        <strong style={{ color: "var(--ink)" }}>Next action:</strong>{" "}
        <span style={{ color: "var(--ink-soft)" }}>{rec.next_action}</span>
      </div>
      {rec.recommendation_context ? (
        <div className="small" style={{ color: "var(--ink-faint)" }}>
          Based on {rec.recommendation_context.canon_chunks_used} canon excerpts,{" "}
          {rec.recommendation_context.updates_included} updates, and{" "}
          {rec.recommendation_context.reviews_included} review notes.
        </div>
      ) : null}
    </div>
  );
}

function UnblockAnalysisView({ rec }: { rec: Rec }) {
  const a = rec.unblock_analysis;
  if (!a) return null;
  return (
    <div
      style={{
        marginTop: 14,
        borderLeft: "4px solid var(--danger)",
        background: "color-mix(in oklch, var(--danger) 6%, transparent)",
        padding: "16px 18px",
        borderRadius: 6,
      }}
    >
      <div style={{ fontSize: 14, color: "var(--ink-soft)", marginBottom: 8 }}>
        <strong style={{ color: "var(--danger)" }}>Blocker:</strong> {a.blocker_summary}
      </div>
      <div style={{ fontSize: 14, color: "var(--ink-soft)", marginBottom: 16 }}>
        <strong>Root cause:</strong> {a.root_cause_analysis}
      </div>

      <h4 style={{ fontFamily: "inherit", fontSize: 14, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-soft)", margin: "0 0 10px" }}>
        Alternatives
      </h4>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginBottom: 14 }}>
        {a.alternatives.map((alt, i) => (
          <article
            key={`${alt.path}-${i}`}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: 6,
              padding: "12px 14px",
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{alt.path}</div>
            <div style={{ marginBottom: 6 }}>
              <span className="badge">{alt.aligned_standard}</span>
            </div>
            <div className="small">
              <strong>Solves:</strong> {alt.solves}
            </div>
            <div className="small">
              <strong>Trade-off:</strong> {alt.tradeoff}
            </div>
            <div className="small" style={{ marginTop: "0.5rem" }}>
              <strong>First step:</strong> {alt.first_step}
            </div>
          </article>
        ))}
      </div>
      <div className="meta-row" style={{ marginTop: 4 }}>
        <strong>Recommended path:</strong>
        <span>{a.recommended_path}</span>
      </div>
      <div className="small" style={{ color: "var(--ink-faint)" }}>
        <strong>Canon:</strong> {a.canon_reference}
      </div>
      {rec.recommendation_context ? (
        <div className="small" style={{ color: "var(--ink-faint)" }}>
          Based on {rec.recommendation_context.canon_chunks_used} canon excerpts,{" "}
          {rec.recommendation_context.updates_included} updates, and{" "}
          {rec.recommendation_context.reviews_included} review notes.
        </div>
      ) : null}
    </div>
  );
}

// ─── Inline candidates duplicate (flag-gated) ───────────────────────

type Candidates = Awaited<ReturnType<typeof apiClient.getTaskCandidates>>;

function InlineCandidatesPanel({
  candidates,
  showAll,
  filters,
}: {
  candidates: Candidates;
  showAll: boolean;
  filters: TaskFilters;
}) {
  const CONFIDENCE_THRESHOLD = 0.6;
  const visibleCandidates = showAll
    ? candidates
    : candidates.filter((c) => (c.confidence ?? 0) >= CONFIDENCE_THRESHOLD);
  const hiddenCount = candidates.length - visibleCandidates.length;

  const toggleParams = new URLSearchParams();
  if (filters.status) toggleParams.set("status", filters.status);
  if (filters.owner_name) toggleParams.set("owner_name", filters.owner_name);
  if (filters.priority) toggleParams.set("priority", filters.priority);
  if (filters.due_before) toggleParams.set("due_before", filters.due_before);
  if (!showAll) toggleParams.set("show_all_candidates", "1");
  const toggleQuery = toggleParams.toString();
  const toggleHref = toggleQuery ? `/tasks?${toggleQuery}` : "/tasks";

  return (
    <article
      style={{
        background: "var(--surface)",
        border: "2px solid var(--line)",
        borderRadius: 8,
        padding: "24px 26px",
        marginBottom: 32,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "0.75rem",
          marginBottom: "0.5rem",
        }}
      >
        <div>
          <h2 style={{ fontFamily: "inherit", fontSize: 18, margin: 0, color: "var(--ink)", letterSpacing: 0, textTransform: "none" }}>
            Suggested Tasks — Extracted from Sources
          </h2>
          <p style={{ fontSize: 14, color: "var(--ink-soft)", marginTop: 6 }}>
            Action items identified from uploaded documents. Review and add to your task list, or dismiss.
          </p>
        </div>
        <Link href={toggleHref} className="small">
          {showAll
            ? "Hide low-confidence"
            : hiddenCount > 0
              ? `Show all (${hiddenCount} low-confidence hidden)`
              : "Show all"}
        </Link>
      </div>
      <ul className="list">
        {visibleCandidates.length === 0 ? (
          <li className="small">
            {candidates.length === 0
              ? "No suggested tasks found."
              : "No high-confidence candidates — toggle Show all to see possibilities."}
          </li>
        ) : (
          visibleCandidates.map((candidate) => {
            const confidence = candidate.confidence ?? 0;
            const isLow = confidence < CONFIDENCE_THRESHOLD;
            const kind =
              typeof candidate.hints_json?.extraction_kind === "string"
                ? (candidate.hints_json.extraction_kind as string)
                : null;
            return (
              <li key={candidate.id} style={isLow ? { opacity: 0.6 } : undefined}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: "0.75rem",
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <strong>
                      {candidate.title.length > 120
                        ? candidate.title.slice(0, 120) + "…"
                        : candidate.title}
                    </strong>
                    {isLow ? (
                      <span className="badge" style={{ marginLeft: "0.5rem" }}>
                        Possible task
                      </span>
                    ) : null}
                    {kind && kind !== "action_item" ? (
                      <span className="badge" style={{ marginLeft: "0.5rem" }}>
                        {kind}
                      </span>
                    ) : null}
                    <div className="small" style={{ marginTop: "0.25rem" }}>
                      Source #{candidate.source_document_id}
                      {candidate.inferred_owner_name
                        ? ` · Owner: ${candidate.inferred_owner_name}`
                        : ""}
                      {candidate.suggested_priority
                        ? ` · Priority: ${candidate.suggested_priority}`
                        : ""}
                      {candidate.canon_alignment
                        ? ` · Standard: ${candidate.canon_alignment}`
                        : ""}
                      {candidate.source_timestamp
                        ? ` · ${candidate.source_timestamp}`
                        : ""}
                      {confidence > 0
                        ? ` · ${(confidence * 100).toFixed(0)}% confidence`
                        : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.375rem", flexShrink: 0 }}>
                    <ApproveCandidate candidateId={candidate.id} />
                    <DismissCandidate candidateId={candidate.id} />
                  </div>
                </div>
              </li>
            );
          })
        )}
      </ul>
    </article>
  );
}
