import { describe, expect, it } from "vitest";

import { validatePromptValue } from "./dialog-validation";

describe("validatePromptValue", () => {
  it("trims whitespace from the accepted value", () => {
    const out = validatePromptValue("  hello  ", { required: false });
    expect(out.ok).toBe(true);
    if (out.ok) expect(out.value).toBe("hello");
  });

  it("accepts an empty value when not required", () => {
    const out = validatePromptValue("", { required: false });
    expect(out.ok).toBe(true);
    if (out.ok) expect(out.value).toBe("");
  });

  it("rejects an empty value when required", () => {
    const out = validatePromptValue("", { required: true });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.error).toBe("required");
  });

  it("rejects a whitespace-only value when required", () => {
    const out = validatePromptValue("    \n\t ", { required: true });
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.error).toBe("required");
  });

  it("accepts a non-empty value when required", () => {
    const out = validatePromptValue("Recovered footage", { required: true });
    expect(out.ok).toBe(true);
    if (out.ok) expect(out.value).toBe("Recovered footage");
  });
});
