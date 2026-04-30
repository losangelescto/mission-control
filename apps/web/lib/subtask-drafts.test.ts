import { describe, expect, it } from "vitest";

import type { SubTaskDraft } from "@/lib/api/types";

import { pickSelectedDrafts, toggleIndex } from "./subtask-drafts";

const DRAFTS: SubTaskDraft[] = [
  { title: "A", description: "a-desc", canon_reference: "Anticipation" },
  { title: "B", description: "b-desc", canon_reference: "Ownership" },
  { title: "C", description: "c-desc", canon_reference: "Accountability" },
];

describe("pickSelectedDrafts", () => {
  it("returns every draft when nothing is deselected", () => {
    expect(pickSelectedDrafts(DRAFTS, new Set())).toEqual(DRAFTS);
  });

  it("drops the deselected indexes only", () => {
    const out = pickSelectedDrafts(DRAFTS, new Set([1]));
    expect(out.map((d) => d.title)).toEqual(["A", "C"]);
  });

  it("returns empty when every draft is deselected", () => {
    expect(pickSelectedDrafts(DRAFTS, new Set([0, 1, 2]))).toEqual([]);
  });
});

describe("toggleIndex", () => {
  it("adds the index when absent", () => {
    expect([...toggleIndex(new Set(), 1)]).toEqual([1]);
  });

  it("removes the index when present", () => {
    expect([...toggleIndex(new Set([1, 2]), 1)]).toEqual([2]);
  });

  it("does not mutate the source set", () => {
    const src = new Set([1]);
    toggleIndex(src, 1);
    expect([...src]).toEqual([1]);
  });
});
