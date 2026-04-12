"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";

import styles from "./tasks-filters.module.css";

export type TasksFiltersFormProps = {
  statusOptions: string[];
  priorityOptions: string[];
  ownerOptions: string[];
  initialStatus: string;
  initialOwner: string;
  initialPriority: string;
  /** Raw `due_before` query value (ISO); displayed in datetime-local */
  initialDueBeforeIso: string | undefined;
};

/** Convert URL ISO datetime to value for `date` input (YYYY-MM-DD). */
export function isoToDateValue(iso: string | undefined): string {
  if (!iso?.trim()) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function TasksFiltersForm({
  statusOptions,
  priorityOptions,
  ownerOptions,
  initialStatus,
  initialOwner,
  initialPriority,
  initialDueBeforeIso,
}: TasksFiltersFormProps) {
  const router = useRouter();

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const params = new URLSearchParams();

    const status = (fd.get("status") as string) || "";
    if (status) params.set("status", status);

    const owner = (fd.get("owner_name") as string) || "";
    if (owner) params.set("owner_name", owner);

    const priority = (fd.get("priority") as string) || "";
    if (priority) params.set("priority", priority);

    const dueRaw = (fd.get("due_before") as string) || "";
    if (dueRaw.trim()) {
      // date input gives YYYY-MM-DD; send end-of-day as ISO
      const d = new Date(dueRaw + "T23:59:59");
      if (!Number.isNaN(d.getTime())) {
        params.set("due_before", d.toISOString());
      }
    }

    const q = params.toString();
    router.push(q ? `/tasks?${q}` : "/tasks");
  }

  const dueLocal = isoToDateValue(initialDueBeforeIso);

  return (
    <form onSubmit={onSubmit} className="grid cols-3">
      <label className="stack-sm">
        <span className="small">Status</span>
        <select name="status" className={styles.select} defaultValue={initialStatus}>
          <option value="">All</option>
          {statusOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="stack-sm">
        <span className="small">Owner</span>
        <select name="owner_name" className={styles.select} defaultValue={initialOwner}>
          <option value="">All</option>
          {ownerOptions.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
      <label className="stack-sm">
        <span className="small">Priority</span>
        <select name="priority" className={styles.select} defaultValue={initialPriority}>
          <option value="">All</option>
          {priorityOptions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <label className="stack-sm">
        <span className="small">Due Before</span>
        <input
          type="date"
          name="due_before"
          className={styles.datetime}
          defaultValue={dueLocal}
          autoComplete="off"
        />
      </label>
      <label className="stack-sm">
        <span className="small">&nbsp;</span>
        <button type="submit" className="link-btn" style={{ height: 46 }}>
          Apply
        </button>
      </label>
    </form>
  );
}
