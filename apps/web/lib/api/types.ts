export type TaskStatus =
  | "backlog"
  | "up_next"
  | "in_progress"
  | "blocked"
  | "completed";

export type SourceType =
  | "canon_doc"
  | "thread_export"
  | "transcript"
  | "note"
  | "board_seed";

export type TaskFilterOptions = {
  statuses: string[];
  priorities: string[];
  owners: string[];
};

export type Task = {
  id: number;
  title: string;
  description: string;
  objective: string;
  standard: string;
  status: TaskStatus;
  priority: string;
  owner_name: string;
  assigner_name: string;
  due_at: string | null;
  source_confidence: number | null;
  created_at: string;
  updated_at: string;
};

export type TaskUpdate = {
  id: number;
  task_id: number;
  update_type: string;
  summary: string;
  what_happened: string;
  options_considered: string;
  steps_taken: string;
  next_step: string;
  created_by: string;
  created_at: string;
};

export type SourceDocument = {
  id: number;
  filename: string;
  source_type: SourceType;
  canonical_doc_id: string | null;
  version_label: string | null;
  is_active_canon_version: boolean;
  extracted_text: string;
  source_path: string;
  created_at: string;
};

export type TaskCandidate = {
  id: number;
  source_document_id: number;
  title: string;
  description: string;
  inferred_owner_name: string | null;
  inferred_due_at: string | null;
  fallback_due_at: string | null;
  review_status: string;
  confidence: number | null;
  created_at: string;
};

export type DailyReviewItem = {
  task_id: number;
  title: string;
  owner_name: string;
  status: string;
  priority: string;
  due_at: string | null;
  reason: string;
};

export type DailyReview = {
  urgent: DailyReviewItem[];
  blocked: DailyReviewItem[];
  stale: DailyReviewItem[];
  due_soon: DailyReviewItem[];
  recurring_due: {
    occurrence_id: number;
    recurrence_template_id: number;
    task_id: number | null;
    occurrence_date: string;
    status: string;
  }[];
  candidate_review: TaskCandidate[];
};

export type MetricsSummary = {
  average_task_age_days: number;
  overdue_count: number;
  blocked_count: number;
  repeat_misses: number;
  candidate_review_queue_size: number;
  total_tasks: number;
};

export type OwnerMetrics = {
  owner_name: string;
  total_tasks: number;
  completed_tasks: number;
  completion_rate: number;
  overdue_tasks: number;
  blocked_tasks: number;
  delegation_count: number;
  delegation_drift_count: number;
};

export type MetricsByOwner = {
  owners: OwnerMetrics[];
};

export type StandardScore = {
  id: number;
  scope_type: string;
  scope_id: string;
  metric_type: string;
  metric_name: string;
  score: number | null;
  assessment: string;
  period: string;
  updated_by: string;
  created_at: string;
};

export type ReviewCadenceType = "daily" | "weekly" | "monthly" | "quarterly" | "ad_hoc";

export type ReviewSession = {
  id: number;
  task_id: number | null;
  owner_name: string | null;
  reviewer: string;
  notes: string;
  action_items: string;
  cadence_type: ReviewCadenceType;
  next_review_date: string | null;
  created_at: string;
};

export type CadenceStatus = {
  cadence: string;
  window_days: number;
  last_review: string | null;
  overdue: boolean;
};

export type UnblockAlternative = {
  path: string;
  solves: string;
  tradeoff: string;
  first_step: string;
  aligned_standard: string;
};

export type UnblockAnalysis = {
  blocker_summary: string;
  root_cause_analysis: string;
  alternatives: UnblockAlternative[];
  recommended_path: string;
  canon_reference: string;
};

export type RecommendationContextMeta = {
  canon_chunks_used: number;
  updates_included: number;
  reviews_included: number;
  blocker_active: boolean;
};

export type Recommendation = {
  id: number;
  task_id: number;
  objective: string;
  standard: string;
  first_principles_plan: string;
  viable_options: string[];
  next_action: string;
  source_refs: Record<string, unknown>[];
  created_at: string;
  recommendation_type: "standard" | "unblock";
  recommendation_context: RecommendationContextMeta | null;
  unblock_analysis: UnblockAnalysis | null;
};

export type RecommendationHistoryItem = {
  id: number;
  task_id: number;
  recommendation_type: "standard" | "unblock";
  created_at: string;
  objective: string;
  standard: string;
  next_action: string;
};
