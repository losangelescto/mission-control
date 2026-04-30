// Pure validators and option lists for the Block / Unblock flow. Extracted
// so they can be vitest-tested without a DOM (this repo's vitest config
// is environment: "node" and only includes lib/**/*.test.ts).

export const BLOCKER_TYPES = [
  "external_dependency",
  "internal_dependency",
  "decision_pending",
  "resource_unavailable",
  "information_missing",
  "technical",
  "other",
] as const;
export type BlockerType = (typeof BLOCKER_TYPES)[number];

export const SEVERITIES = ["low", "medium", "high", "critical"] as const;
export type Severity = (typeof SEVERITIES)[number];

// Statuses the task is allowed to transition into when unblocked. We
// deliberately exclude "blocked" and "backlog" so unblock means progress.
export const UNBLOCK_NEXT_STATUSES = ["in_progress", "up_next", "completed"] as const;
export type UnblockNextStatus = (typeof UNBLOCK_NEXT_STATUSES)[number];

export type BlockFormInput = {
  blocker_type: string;
  blocker_reason: string;
  severity: string;
};

export type UnblockFormInput = {
  resolution_notes: string;
  next_status: string;
};

export type ValidationResult<T> =
  | { ok: true; payload: T }
  | { ok: false; errors: Record<string, string> };

const REASON_MAX = 1000;

export function validateBlockForm(
  input: BlockFormInput,
): ValidationResult<{ blocker_type: BlockerType; blocker_reason: string; severity: Severity }> {
  const errors: Record<string, string> = {};
  const reason = input.blocker_reason.trim();
  if (!reason) errors.blocker_reason = "Required";
  else if (reason.length > REASON_MAX) errors.blocker_reason = `Max ${REASON_MAX} chars`;
  if (!(BLOCKER_TYPES as readonly string[]).includes(input.blocker_type))
    errors.blocker_type = "Pick a blocker type";
  if (!(SEVERITIES as readonly string[]).includes(input.severity))
    errors.severity = "Pick a severity";
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    payload: {
      blocker_type: input.blocker_type as BlockerType,
      blocker_reason: reason,
      severity: input.severity as Severity,
    },
  };
}

export function validateUnblockForm(
  input: UnblockFormInput,
): ValidationResult<{ resolution_notes: string; next_status: UnblockNextStatus }> {
  const errors: Record<string, string> = {};
  if (!(UNBLOCK_NEXT_STATUSES as readonly string[]).includes(input.next_status))
    errors.next_status = "Pick a next status";
  // resolution_notes is encouraged but not required — we do not block submit.
  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    payload: {
      resolution_notes: input.resolution_notes.trim(),
      next_status: input.next_status as UnblockNextStatus,
    },
  };
}
