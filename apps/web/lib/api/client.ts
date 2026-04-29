import {
  CadenceStatus,
  CanonChangeEventDetail,
  CanonChangeEventSummary,
  CanonChangeListResponse,
  DailyReview,
  MetricsByOwner,
  MetricsSummary,
  Obstacle,
  Recommendation,
  RecommendationHistoryItem,
  ReviewSession,
  SearchMode,
  SearchResponse,
  SearchTypeFilter,
  SubTask,
  SubTaskGeneratePreviewResponse,
  SourceDocument,
  SourceProcessingStatus,
  StandardScore,
  Task,
  TaskCandidate,
  TaskFilterOptions,
  TaskStatus,
  TaskUpdate,
} from "@/lib/api/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API request failed (${response.status}): ${detail}`);
  }
  return (await response.json()) as T;
}

export type TaskFilters = {
  status?: TaskStatus;
  owner_name?: string;
  due_before?: string;
  priority?: string;
};

export const apiClient = {
  async getDailyReview(): Promise<DailyReview> {
    return apiFetch<DailyReview>("/review/daily");
  },

  async getTaskFilterOptions(): Promise<TaskFilterOptions> {
    return apiFetch<TaskFilterOptions>("/tasks/filter-options");
  },

  async getTasks(filters: TaskFilters = {}): Promise<Task[]> {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.owner_name) params.set("owner_name", filters.owner_name);
    if (filters.due_before) params.set("due_before", filters.due_before);
    if (filters.priority) params.set("priority", filters.priority);
    const query = params.toString();
    return apiFetch<Task[]>(`/tasks${query ? `?${query}` : ""}`);
  },

  async getTask(taskId: number): Promise<Task> {
    return apiFetch<Task>(`/tasks/${taskId}`);
  },

  async getTaskUpdates(taskId: number): Promise<TaskUpdate[]> {
    return apiFetch<TaskUpdate[]>(`/tasks/${taskId}/updates`);
  },

  async updateTask(taskId: number, updates: Partial<Task>): Promise<Task> {
    return apiFetch<Task>(`/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
  },

  async createTaskUpdate(
    taskId: number,
    payload: {
      update_type: string;
      summary: string;
      what_happened: string;
      options_considered: string;
      steps_taken: string;
      next_step: string;
      created_by: string;
    }
  ): Promise<TaskUpdate> {
    return apiFetch<TaskUpdate>(`/tasks/${taskId}/updates`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getSources(): Promise<SourceDocument[]> {
    return apiFetch<SourceDocument[]>("/sources");
  },

  async getSource(sourceId: number): Promise<SourceDocument> {
    return apiFetch<SourceDocument>(`/sources/${sourceId}`);
  },

  async getSourceStatus(sourceId: number): Promise<SourceProcessingStatus> {
    return apiFetch<SourceProcessingStatus>(`/sources/${sourceId}/status`);
  },

  async getTaskCandidates(reviewStatus?: string): Promise<TaskCandidate[]> {
    const query = reviewStatus
      ? `?${new URLSearchParams({ review_status: reviewStatus }).toString()}`
      : "";
    return apiFetch<TaskCandidate[]>(`/task-candidates${query}`);
  },

  async getActiveCanon(): Promise<SourceDocument[]> {
    return apiFetch<SourceDocument[]>("/canon/active");
  },

  async getCanonChanges(onlyUnreviewed = false): Promise<CanonChangeListResponse> {
    const query = onlyUnreviewed ? "?only_unreviewed=true" : "";
    return apiFetch<CanonChangeListResponse>(`/canon/changes${query}`);
  },

  async getCanonChange(eventId: number): Promise<CanonChangeEventDetail> {
    return apiFetch<CanonChangeEventDetail>(`/canon/changes/${eventId}`);
  },

  async acknowledgeCanonChange(eventId: number): Promise<CanonChangeEventSummary> {
    return apiFetch<CanonChangeEventSummary>(
      `/canon/changes/${eventId}/acknowledge`,
      { method: "POST", body: "{}" },
    );
  },

  async getMetricsSummary(): Promise<MetricsSummary> {
    return apiFetch<MetricsSummary>("/metrics/summary");
  },

  async getMetricsByOwner(): Promise<MetricsByOwner> {
    return apiFetch<MetricsByOwner>("/metrics/by-owner");
  },

  async generateRecommendation(taskId: number): Promise<Recommendation> {
    return apiFetch<Recommendation>(`/tasks/${taskId}/recommendation`, {
      method: "POST",
    });
  },

  async listTaskRecommendations(taskId: number): Promise<RecommendationHistoryItem[]> {
    return apiFetch<RecommendationHistoryItem[]>(`/tasks/${taskId}/recommendations`);
  },

  async getReviews(params?: {
    task_id?: number;
    owner?: string;
  }): Promise<ReviewSession[]> {
    const q = new URLSearchParams();
    if (params?.task_id) q.set("task_id", String(params.task_id));
    if (params?.owner) q.set("owner", params.owner);
    const query = q.toString();
    return apiFetch<ReviewSession[]>(`/reviews${query ? `?${query}` : ""}`);
  },

  async getCadenceStatus(): Promise<CadenceStatus[]> {
    return apiFetch<CadenceStatus[]>("/reviews/cadence-status");
  },

  async getStandardScores(params?: {
    scope_type?: string;
    scope_id?: string;
    metric_type?: string;
    period?: string;
  }): Promise<StandardScore[]> {
    const q = new URLSearchParams();
    if (params?.scope_type) q.set("scope_type", params.scope_type);
    if (params?.scope_id) q.set("scope_id", params.scope_id);
    if (params?.metric_type) q.set("metric_type", params.metric_type);
    if (params?.period) q.set("period", params.period);
    const query = q.toString();
    return apiFetch<StandardScore[]>(`/standard-scores${query ? `?${query}` : ""}`);
  },

  async listSubTasks(taskId: number): Promise<SubTask[]> {
    return apiFetch<SubTask[]>(`/tasks/${taskId}/subtasks`);
  },

  async createSubTask(
    taskId: number,
    payload: { title: string; description?: string; canon_reference?: string },
  ): Promise<SubTask> {
    return apiFetch<SubTask>(`/tasks/${taskId}/subtasks`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateSubTask(
    subTaskId: number,
    payload: { title?: string; description?: string; status?: string; canon_reference?: string; order?: number },
  ): Promise<SubTask> {
    return apiFetch<SubTask>(`/subtasks/${subTaskId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async deleteSubTask(subTaskId: number): Promise<void> {
    await fetch(`${API_BASE_URL}/subtasks/${subTaskId}`, {
      method: "DELETE",
    });
  },

  async generateSubTasks(taskId: number): Promise<SubTaskGeneratePreviewResponse> {
    return apiFetch<SubTaskGeneratePreviewResponse>(
      `/tasks/${taskId}/subtasks/generate`,
      { method: "POST" },
    );
  },

  async listObstacles(taskId: number): Promise<Obstacle[]> {
    return apiFetch<Obstacle[]>(`/tasks/${taskId}/obstacles`);
  },

  async createObstacle(
    taskId: number,
    payload: { description: string; impact?: string; identified_by?: string },
  ): Promise<Obstacle> {
    return apiFetch<Obstacle>(`/tasks/${taskId}/obstacles`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async analyzeObstacle(obstacleId: number): Promise<Obstacle> {
    return apiFetch<Obstacle>(`/obstacles/${obstacleId}/analyze`, {
      method: "POST",
    });
  },

  async resolveObstacle(obstacleId: number, resolutionNotes: string): Promise<Obstacle> {
    return apiFetch<Obstacle>(`/obstacles/${obstacleId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution_notes: resolutionNotes }),
    });
  },

  async search(
    q: string,
    options: {
      type?: SearchTypeFilter;
      mode?: SearchMode;
      limit?: number;
      offset?: number;
      signal?: AbortSignal;
    } = {},
  ): Promise<SearchResponse> {
    const params = new URLSearchParams({ q });
    if (options.type) params.set("type", options.type);
    if (options.mode) params.set("mode", options.mode);
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.offset !== undefined) params.set("offset", String(options.offset));
    const response = await fetch(`${API_BASE_URL}/search?${params.toString()}`, {
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      signal: options.signal,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Search failed (${response.status}): ${detail}`);
    }
    return (await response.json()) as SearchResponse;
  },
};
