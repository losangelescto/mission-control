import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";

describe("apiClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds query params for task filters", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })
      );

    await apiClient.getTasks({
      status: "blocked",
      owner_name: "Alex",
      priority: "high",
      due_before: "2026-04-01T00:00:00Z",
    });

    const firstCall = fetchSpy.mock.calls[0];
    expect(firstCall?.[0]).toBe(
      "http://localhost:8000/tasks?status=blocked&owner_name=Alex&due_before=2026-04-01T00%3A00%3A00Z&priority=high"
    );
  });

  it("fetches task filter options", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          statuses: ["backlog"],
          priorities: ["low"],
          owners: ["Alex"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const out = await apiClient.getTaskFilterOptions();

    expect(fetchSpy.mock.calls[0]?.[0]).toBe("http://localhost:8000/tasks/filter-options");
    expect(out.owners).toEqual(["Alex"]);
  });

  it("uses post method for recommendation generation", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            id: 1,
            task_id: 1,
            objective: "obj",
            standard: "std",
            first_principles_plan: "plan",
            viable_options: ["a", "b"],
            next_action: "next",
            source_refs: [],
            created_at: "2026-01-01T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );

    await apiClient.generateRecommendation(1);

    const firstCall = fetchSpy.mock.calls[0];
    expect(firstCall?.[0]).toBe("http://localhost:8000/tasks/1/recommendation");
    expect((firstCall?.[1] as RequestInit).method).toBe("POST");
  });
});
