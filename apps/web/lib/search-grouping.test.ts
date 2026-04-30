import { describe, expect, it } from "vitest";

import type { SearchResult } from "@/lib/api/types";

import { TYPE_LABEL, groupSearchResults } from "./search-grouping";

function r(type: SearchResult["type"], id: number, title: string, snippet = ""): SearchResult {
  return {
    id,
    type,
    title,
    snippet,
    relevance: 1,
    url: `/x/${id}`,
    metadata: {},
  };
}

describe("groupSearchResults", () => {
  it("returns no groups for empty / null / undefined input", () => {
    expect(groupSearchResults([])).toEqual([]);
    expect(groupSearchResults(null)).toEqual([]);
    expect(groupSearchResults(undefined)).toEqual([]);
  });

  it("buckets task / task_update / sub_task / obstacle into Tasks", () => {
    const results = [
      r("task", 1, "T"),
      r("task_update", 2, "U"),
      r("sub_task", 3, "S"),
      r("obstacle", 4, "O"),
    ];
    const groups = groupSearchResults(results);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("tasks");
    expect(groups[0].items).toHaveLength(4);
  });

  it("buckets source AND source_chunk into the same Sources group", () => {
    const results = [r("source", 1, "doc"), r("source_chunk", 2, "chunk")];
    const groups = groupSearchResults(results);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("sources");
    expect(groups[0].items.map((i) => i.type)).toEqual(["source", "source_chunk"]);
  });

  it("preserves the canonical group order: tasks → sources → reviews → canon", () => {
    const results = [
      r("canon", 1, "C"),
      r("review", 2, "R"),
      r("source", 3, "S"),
      r("task", 4, "T"),
    ];
    const keys = groupSearchResults(results).map((g) => g.key);
    expect(keys).toEqual(["tasks", "sources", "reviews", "canon"]);
  });

  it("renders mixed-type result list with snippet text intact for downstream UI", () => {
    const results = [
      r("task", 1, "Roof quote", "Pull a <mark>roof</mark> quote from the contractor"),
      r("task", 2, "Roof inspection", "<mark>roof</mark> inspection report came back"),
      r("source", 3, "vendor.pdf", "the <mark>roof</mark> section needs attention"),
    ];
    const groups = groupSearchResults(results);
    expect(groups).toHaveLength(2);
    expect(groups[0].items).toHaveLength(2);
    expect(groups[1].items).toHaveLength(1);
    expect(groups[0].items[0].snippet).toContain("<mark>roof</mark>");
    expect(groups[1].items[0].snippet).toContain("<mark>roof</mark>");
  });

  it("drops result types not in any bucket without throwing", () => {
    const results = [
      r("task", 1, "T"),
      // Force an unknown type past the TS guard to simulate API drift.
      ({ ...r("task", 99, "X"), type: "future_kind" } as unknown) as SearchResult,
    ];
    const groups = groupSearchResults(results);
    expect(groups).toHaveLength(1);
    expect(groups[0].items).toHaveLength(1);
    expect(groups[0].items[0].id).toBe(1);
  });

  it("TYPE_LABEL covers every defined SearchResultType", () => {
    for (const type of [
      "task", "task_update", "sub_task", "obstacle",
      "source", "source_chunk", "review", "canon",
    ] as const) {
      expect(TYPE_LABEL[type]).toBeTruthy();
    }
  });
});
