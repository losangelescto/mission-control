import { describe, expect, it } from "vitest";

import { validateBlockForm, validateUnblockForm } from "./block-flow";

describe("validateBlockForm", () => {
  it("accepts a fully-populated valid payload", () => {
    const out = validateBlockForm({
      blocker_type: "external_dependency",
      blocker_reason: "Vendor hasn't returned the signed SoW",
      severity: "high",
    });
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.payload.blocker_type).toBe("external_dependency");
      expect(out.payload.blocker_reason).toBe("Vendor hasn't returned the signed SoW");
      expect(out.payload.severity).toBe("high");
    }
  });

  it("rejects an empty or whitespace-only reason", () => {
    const out = validateBlockForm({
      blocker_type: "external_dependency",
      blocker_reason: "   ",
      severity: "medium",
    });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.errors.blocker_reason).toBe("Required");
  });

  it("rejects an unknown blocker_type", () => {
    const out = validateBlockForm({
      blocker_type: "magic",
      blocker_reason: "any",
      severity: "high",
    });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.errors.blocker_type).toBeTruthy();
  });

  it("rejects an unknown severity", () => {
    const out = validateBlockForm({
      blocker_type: "technical",
      blocker_reason: "any",
      severity: "extreme",
    });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.errors.severity).toBeTruthy();
  });

  it("trims the reason before submitting", () => {
    const out = validateBlockForm({
      blocker_type: "internal_dependency",
      blocker_reason: "  legal review  ",
      severity: "low",
    });
    expect(out.ok).toBe(true);
    if (out.ok) expect(out.payload.blocker_reason).toBe("legal review");
  });
});

describe("validateUnblockForm", () => {
  it("accepts an empty resolution note (encouraged, not required)", () => {
    const out = validateUnblockForm({ resolution_notes: "", next_status: "in_progress" });
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.payload.resolution_notes).toBe("");
      expect(out.payload.next_status).toBe("in_progress");
    }
  });

  it("trims the resolution note", () => {
    const out = validateUnblockForm({
      resolution_notes: "  vendor confirmed delivery  ",
      next_status: "completed",
    });
    expect(out.ok).toBe(true);
    if (out.ok) expect(out.payload.resolution_notes).toBe("vendor confirmed delivery");
  });

  it("rejects an unknown next_status", () => {
    const out = validateUnblockForm({ resolution_notes: "x", next_status: "blocked" });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.errors.next_status).toBeTruthy();
  });
});
