// Pure helpers backing the UploadSource form. Extracted so the bug-fix
// rule ("never overwrite a user's source-type selection with a filename
// inference") can be vitest-tested under the node environment without
// rendering React.

import type { SourceType } from "./api/types";

const EXT_TO_TYPE: Record<string, SourceType> = {
  pdf: "thread_export",
  docx: "canon_doc",
  txt: "note",
  md: "note",
  mp3: "transcript",
  m4a: "transcript",
  wav: "transcript",
  ogg: "transcript",
  flac: "transcript",
  mp4: "transcript",
  webm: "transcript",
  mov: "transcript",
};

export function inferSourceType(filename: string): SourceType {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return (EXT_TO_TYPE[ext] as SourceType) ?? "note";
}

export type ResolveInput = {
  current: SourceType;
  filename: string;
  userExplicitlySetType: boolean;
};

// Returns the SourceType the form should hold after a file pick. The rule:
// the user's explicit selection always wins. Inference only applies when
// the user has not touched the source-type select since the form opened.
export function resolveSourceTypeAfterFilePick(input: ResolveInput): SourceType {
  if (input.userExplicitlySetType) return input.current;
  return inferSourceType(input.filename);
}
