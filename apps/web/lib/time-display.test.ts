import { describe, expect, it } from "vitest";

import { formatIsoForLocal, formatIsoForSsr } from "./time-display";

const ISO = "2026-04-30T08:30:00Z";

describe("formatIsoForSsr", () => {
  it("returns a deterministic UTC datetime regardless of host timezone", () => {
    const out = formatIsoForSsr(ISO);
    // 08:30 UTC → "Apr 30, 2026, 8:30 AM" everywhere.
    expect(out).toContain("Apr 30, 2026");
    expect(out).toContain("8:30");
    expect(out).toContain("AM");
  });

  it("omits the time component for the date-only format", () => {
    const out = formatIsoForSsr(ISO, "date");
    expect(out).toBe("Apr 30, 2026");
  });

  it("never depends on the host timezone — output is identical to a pinned UTC formatter", () => {
    const out = formatIsoForSsr(ISO);
    const pinned = new Date(ISO).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "UTC",
    });
    expect(out).toBe(pinned);
  });
});

describe("formatIsoForLocal", () => {
  it("returns a string with the same date components for the date format", () => {
    // Date-only formatting is timezone-stable for any time well inside a day.
    expect(formatIsoForLocal(ISO, "date")).toBe("Apr 30, 2026");
  });

  it("returns a non-empty datetime string", () => {
    const out = formatIsoForLocal(ISO);
    expect(out.length).toBeGreaterThan(0);
    expect(out).toContain("2026");
  });
});
