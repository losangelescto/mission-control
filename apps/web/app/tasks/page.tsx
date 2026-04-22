import { apiClient, TaskFilters } from "@/lib/api/client";
import { firstSearchParam, parsePositiveIntParam } from "@/lib/search-params";
import Link from "next/link";
import { TasksFiltersForm } from "./TasksFiltersForm";
import { TaskNotes } from "./TaskNotes";
import { TaskUpdateInput } from "./TaskUpdateInput";
import { TaskStatusSelect } from "./TaskStatusSelect";
import { ApproveCandidate } from "./ApproveCandidate";
import { DismissCandidate } from "./DismissCandidate";

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

  const selectedFromQuery = parsePositiveIntParam(params.selected);
  const selectedId = selectedFromQuery ?? tasks[0]?.id;
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

  let recommendation: Awaited<ReturnType<typeof apiClient.generateRecommendation>> | null = null;
  if (selectedTask && firstSearchParam(params.generate_recommendation) === "1") {
    recommendation = await apiClient.generateRecommendation(selectedTask.id).catch(() => null);
  }

  const recommendationHistory = selectedTask
    ? await apiClient.listTaskRecommendations(selectedTask.id).catch(() => [])
    : [];

  const candidates = await apiClient.getTaskCandidates("pending_review").catch(() => []);

  // Build query string to preserve current filters when selecting a task
  const filterQuery = new URLSearchParams();
  if (filters.status) filterQuery.set("status", filters.status);
  if (filters.owner_name) filterQuery.set("owner_name", filters.owner_name);
  if (filters.priority) filterQuery.set("priority", filters.priority);
  if (filters.due_before) filterQuery.set("due_before", filters.due_before);
  const filterPrefix = filterQuery.toString();

  function taskHref(taskId: number): string {
    const parts = filterPrefix ? `${filterPrefix}&selected=${taskId}` : `selected=${taskId}`;
    return `/tasks?${parts}`;
  }

  return (
    <section className="stack">
      <div className="panel">
        <h1>Tasks</h1>
      </div>

      {tasksError ? (
        <article className="panel" role="alert">
          <h2>Could not load tasks</h2>
          <p className="small">{tasksError}</p>
          <p className="small">
            Start the API (for example{" "}
            <code>uvicorn app.main:app --reload --port 8000</code> from{" "}
            <code>apps/api</code>) and ensure <code>NEXT_PUBLIC_API_URL</code> in{" "}
            <code>apps/web/.env.local</code> matches.
          </p>
        </article>
      ) : null}

      <article className="panel">
        <h2>Filters</h2>
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

      <div className="grid cols-2">
        <article className="panel">
          <h2>Task List</h2>
          <ul className="list">
            {tasks.length === 0 ? (
              <li className="small">No tasks found for current filters.</li>
            ) : (
              tasks.map((task) => (
                <li key={task.id}>
                  <Link href={taskHref(task.id)}>
                    <strong>{task.title}</strong>
                  </Link>
                  <div className="meta-row" style={{ marginTop: "0.25rem", flexWrap: "wrap" }}>
                    <span data-status={task.status}>{task.status}</span>
                    <span>Owner: {task.owner_name}</span>
                    <span>{task.priority}</span>
                    {task.due_at ? (
                      <span>Due: {new Date(task.due_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
                    ) : null}
                  </div>
                </li>
              ))
            )}
          </ul>
        </article>

        <article className="panel">
          <h2>Task Detail</h2>
          {selectedTask ? (
            <div className="stack-sm">
              <div>
                <strong>{selectedTask.title}</strong>
              </div>
              <TaskStatusSelect taskId={selectedTask.id} initialStatus={selectedTask.status} />
              <div className="meta-row">Owner: {selectedTask.owner_name}</div>
              <div className="meta-row">Due: {selectedTask.due_at ? new Date(selectedTask.due_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "-"}</div>
              <div className="meta-row">
                Blocker Status:{" "}
                {blockedSet.has(selectedTask.id)
                  ? <span data-status="blocked">blocked</span>
                  : "not blocked"}
              </div>
              <div className="meta-row">
                Recurrence Info: {recurringForTask.length} linked due occurrence(s)
              </div>
              <TaskNotes taskId={selectedTask.id} initialDescription={selectedTask.description} updatedAt={selectedTask.updated_at} />
              <TaskUpdateInput taskId={selectedTask.id} initialUpdates={[...updates].reverse()} />
            </div>
          ) : (
            <p className="small">No task selected.</p>
          )}
        </article>
      </div>

      {selectedTask ? (
        recommendation && recommendation.recommendation_type === "unblock" && recommendation.unblock_analysis ? (
          <article
            className="panel"
            style={{
              borderLeft: "4px solid var(--red)",
              background: "var(--red-dim)",
            }}
          >
            <h2 style={{ color: "var(--red)" }}>Unblock Analysis</h2>
            <div className="stack-sm">
              <Link
                className="link-btn"
                href={`/tasks?selected=${selectedTask.id}&generate_recommendation=1`}
              >
                Regenerate Analysis
              </Link>

              <div className="small">
                <strong>Blocker:</strong> {recommendation.unblock_analysis.blocker_summary}
              </div>
              <div className="small">
                <strong>Root cause:</strong> {recommendation.unblock_analysis.root_cause_analysis}
              </div>

              <h3 style={{ marginTop: "0.75rem" }}>Alternatives</h3>
              <div className="grid cols-3">
                {recommendation.unblock_analysis.alternatives.map((alt, i) => (
                  <article
                    key={`${alt.path}-${i}`}
                    className="panel"
                    style={{ background: "var(--bg-base)" }}
                  >
                    <h3>{alt.path}</h3>
                    <div className="small" style={{ marginBottom: "0.375rem" }}>
                      <span className="badge">{alt.aligned_standard}</span>
                    </div>
                    <div className="small"><strong>Solves:</strong> {alt.solves}</div>
                    <div className="small"><strong>Trade-off:</strong> {alt.tradeoff}</div>
                    <div className="small" style={{ marginTop: "0.5rem" }}>
                      <strong>First step:</strong> {alt.first_step}
                    </div>
                  </article>
                ))}
              </div>

              <div className="meta-row" style={{ marginTop: "0.75rem" }}>
                <strong>Recommended path:</strong>
                <span>{recommendation.unblock_analysis.recommended_path}</span>
              </div>
              <div className="small" style={{ color: "var(--text-tertiary)" }}>
                <strong>Canon:</strong> {recommendation.unblock_analysis.canon_reference}
              </div>
              {recommendation.recommendation_context ? (
                <div className="small" style={{ color: "var(--text-tertiary)" }}>
                  Based on {recommendation.recommendation_context.canon_chunks_used} canon excerpts,{" "}
                  {recommendation.recommendation_context.updates_included} updates, and{" "}
                  {recommendation.recommendation_context.reviews_included} review notes.
                </div>
              ) : null}
            </div>
          </article>
        ) : (
          <article className="panel">
            <h2>Recommendation</h2>
            <div className="stack-sm">
              <Link
                className="link-btn"
                href={`/tasks?selected=${selectedTask.id}&generate_recommendation=1`}
              >
                Generate Recommendation
              </Link>
              {recommendation ? (
                <>
                  <div className="small">
                    <strong>Objective:</strong> {recommendation.objective}
                  </div>
                  <div className="small">
                    <strong>Standard:</strong> {recommendation.standard}
                  </div>
                  <div className="small">{recommendation.first_principles_plan}</div>
                  <ul className="list">
                    {recommendation.viable_options.map((option) => (
                      <li key={option} className="small">
                        {option}
                      </li>
                    ))}
                  </ul>
                  <div className="small">
                    <strong>Next Action:</strong> {recommendation.next_action}
                  </div>
                  {recommendation.recommendation_context ? (
                    <div className="small" style={{ color: "var(--text-tertiary)" }}>
                      Based on {recommendation.recommendation_context.canon_chunks_used} canon excerpts,{" "}
                      {recommendation.recommendation_context.updates_included} updates, and{" "}
                      {recommendation.recommendation_context.reviews_included} review notes.
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="small">Generate to view the latest recommendation.</p>
              )}
            </div>
          </article>
        )
      ) : (
        <article className="panel">
          <h2>Recommendation</h2>
          <p className="small">Select a task first.</p>
        </article>
      )}

      {selectedTask && recommendationHistory.length > 0 ? (
        <article className="panel">
          <details>
            <summary>Previous Recommendations ({recommendationHistory.length})</summary>
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
        </article>
      ) : null}

      <article className="panel">
        <h2>Suggested Tasks — Extracted from Sources</h2>
        <p className="small" style={{ marginBottom: "0.5rem" }}>
          Action items identified from uploaded documents. Review and add to your task list, or dismiss.
        </p>
        <ul className="list">
          {candidates.length === 0 ? (
            <li className="small">No suggested tasks found.</li>
          ) : (
            candidates.map((candidate) => (
              <li key={candidate.id}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem" }}>
                  <div style={{ minWidth: 0 }}>
                    <strong>{candidate.title.length > 120 ? candidate.title.slice(0, 120) + "…" : candidate.title}</strong>
                    <div className="small" style={{ marginTop: "0.25rem" }}>
                      Source #{candidate.source_document_id}
                      {candidate.inferred_owner_name ? ` · Owner: ${candidate.inferred_owner_name}` : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.375rem", flexShrink: 0 }}>
                    <ApproveCandidate candidateId={candidate.id} />
                    <DismissCandidate candidateId={candidate.id} />
                  </div>
                </div>
              </li>
            ))
          )}
        </ul>
      </article>
    </section>
  );
}
