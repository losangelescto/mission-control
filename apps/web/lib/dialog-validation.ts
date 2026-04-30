// Pure validators backing the in-app dialog components (ConfirmDialog,
// PromptDialog). Extracted so the rules can be vitest-tested under the
// node environment without rendering React or instantiating a DOM.

export type PromptValidation =
  | { ok: true; value: string }
  | { ok: false; error: "required" };

export function validatePromptValue(
  raw: string,
  options: { required: boolean },
): PromptValidation {
  const trimmed = raw.trim();
  if (options.required && !trimmed) return { ok: false, error: "required" };
  return { ok: true, value: trimmed };
}
