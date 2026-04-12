import { describe, expect, it } from "vitest";

import { firstSearchParam, parsePositiveIntParam } from "./search-params";

describe("search-params", () => {
  it("firstSearchParam handles string | string[]", () => {
    expect(firstSearchParam(undefined)).toBeUndefined();
    expect(firstSearchParam("a")).toBe("a");
    expect(firstSearchParam(["x", "y"])).toBe("x");
    expect(firstSearchParam([""])).toBeUndefined();
  });

  it("parsePositiveIntParam rejects Number(array) pitfall", () => {
    expect(parsePositiveIntParam(["42"])).toBe(42);
    expect(Number(["1", "2"])).toBeNaN();
    expect(parsePositiveIntParam(["1", "2"])).toBe(1);
    expect(parsePositiveIntParam(undefined)).toBeUndefined();
    expect(parsePositiveIntParam("0")).toBeUndefined();
    expect(parsePositiveIntParam("-1")).toBeUndefined();
    expect(parsePositiveIntParam("3.5")).toBeUndefined();
  });
});
