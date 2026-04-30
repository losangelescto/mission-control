import { describe, expect, it } from "vitest";

import { inferSourceType, resolveSourceTypeAfterFilePick } from "./upload-source";

describe("inferSourceType", () => {
  it("maps mp3/wav/m4a/mp4 to transcript", () => {
    expect(inferSourceType("call.mp3")).toBe("transcript");
    expect(inferSourceType("call.wav")).toBe("transcript");
    expect(inferSourceType("call.m4a")).toBe("transcript");
    expect(inferSourceType("call.mp4")).toBe("transcript");
  });

  it("maps docx to canon_doc and pdf to thread_export", () => {
    expect(inferSourceType("policy.docx")).toBe("canon_doc");
    expect(inferSourceType("thread.pdf")).toBe("thread_export");
  });

  it("falls back to note for unknown extensions and missing extensions", () => {
    expect(inferSourceType("README")).toBe("note");
    expect(inferSourceType("strange.xyz")).toBe("note");
    expect(inferSourceType("")).toBe("note");
  });
});

describe("resolveSourceTypeAfterFilePick", () => {
  it("auto-infers when the user has NOT explicitly set the type", () => {
    const out = resolveSourceTypeAfterFilePick({
      current: "note",
      filename: "vendor-policy.docx",
      userExplicitlySetType: false,
    });
    expect(out).toBe("canon_doc");
  });

  it("preserves the user's explicit selection even when the file extension would map elsewhere", () => {
    // The original bug: user picks canon_doc, then picks a .pdf file →
    // form silently flipped to thread_export. Pin the contract here.
    const out = resolveSourceTypeAfterFilePick({
      current: "canon_doc",
      filename: "evidence-policy.pdf",
      userExplicitlySetType: true,
    });
    expect(out).toBe("canon_doc");
  });

  it("preserves explicit selection across multiple file picks", () => {
    const after_first = resolveSourceTypeAfterFilePick({
      current: "transcript",
      filename: "interview.mp3",
      userExplicitlySetType: true,
    });
    const after_second = resolveSourceTypeAfterFilePick({
      current: after_first,
      filename: "policy.docx",
      userExplicitlySetType: true,
    });
    expect(after_first).toBe("transcript");
    expect(after_second).toBe("transcript");
  });

  it("when user has NOT touched the type, picking a transcript-shaped file infers transcript", () => {
    const out = resolveSourceTypeAfterFilePick({
      current: "note",
      filename: "weekly-call.wav",
      userExplicitlySetType: false,
    });
    expect(out).toBe("transcript");
  });
});
