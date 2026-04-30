import { describe, expect, it } from "vitest";

import { HYPHEN_HINT_TEXT, shouldShowHyphenHint } from "./search-hint";

describe("shouldShowHyphenHint", () => {
  it("shows the hint for a hyphenated query that returned nothing", () => {
    expect(shouldShowHyphenHint("vendor-policy", false)).toBe(true);
  });

  it("shows the hint for an underscored query that returned nothing", () => {
    expect(shouldShowHyphenHint("vendor_policy", false)).toBe(true);
  });

  it("shows the hint for a dotted query that returned nothing", () => {
    expect(shouldShowHyphenHint("vendor.policy", false)).toBe(true);
  });

  it("shows the hint for a slashed query (file paths) that returned nothing", () => {
    expect(shouldShowHyphenHint("vendor/policy", false)).toBe(true);
  });

  it("does NOT show the hint when the query has no separators", () => {
    expect(shouldShowHyphenHint("vendor policy", false)).toBe(false);
    expect(shouldShowHyphenHint("vendor", false)).toBe(false);
    expect(shouldShowHyphenHint("", false)).toBe(false);
  });

  it("does NOT show the hint when results exist, regardless of separators", () => {
    expect(shouldShowHyphenHint("vendor-policy", true)).toBe(false);
  });

  it("hint text references hyphens and separators", () => {
    expect(HYPHEN_HINT_TEXT).toMatch(/hyphen/i);
    expect(HYPHEN_HINT_TEXT).toMatch(/separator/i);
  });
});
