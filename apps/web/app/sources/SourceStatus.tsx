"use client";

import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api/client";
import type {
  SourceProcessingState,
  SourceProcessingStatus,
} from "@/lib/api/types";

const POLL_INTERVAL_MS = 2_000;
const TERMINAL_STATES = new Set<SourceProcessingState>([
  "complete",
  "partial",
  "failed",
]);

// Background = soft tint of the foreground token (color-mix at ~14%) so
// each state reads at a glance without leaving the v2 'Calm' palette.
const BADGE_STYLES: Record<SourceProcessingState, { bg: string; fg: string }> = {
  queued:     { bg: "color-mix(in oklch, var(--ink-faint) 14%, transparent)", fg: "var(--ink-soft)" },
  processing: { bg: "color-mix(in oklch, var(--bronze) 14%, transparent)",    fg: "var(--bronze)"   },
  partial:    { bg: "color-mix(in oklch, var(--warning) 14%, transparent)",   fg: "var(--warning)"  },
  complete:   { bg: "color-mix(in oklch, var(--success) 14%, transparent)",   fg: "var(--success)"  },
  failed:     { bg: "color-mix(in oklch, var(--danger) 14%, transparent)",    fg: "var(--danger)"   },
};

const BADGE_LABELS: Record<SourceProcessingState, string> = {
  queued: "Queued",
  processing: "Processing",
  partial: "Partial",
  complete: "Complete",
  failed: "Failed",
};

type Props = {
  sourceId: number;
  initial: SourceProcessingStatus;
};

export default function SourceStatus({ sourceId, initial }: Props) {
  const [status, setStatus] = useState<SourceProcessingStatus>(initial);

  useEffect(() => {
    if (TERMINAL_STATES.has(status.processing_status)) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const next = await apiClient.getSourceStatus(sourceId);
        if (cancelled) return;
        setStatus(next);
      } catch {
        // Surface nothing — the next tick will retry.
      }
    };
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [sourceId, status.processing_status]);

  const state = status.processing_status;
  const palette = BADGE_STYLES[state];
  const progressLabel = renderProgressLabel(status);

  return (
    <div className="stack-sm">
      <div>
        <span
          className="badge"
          style={{ background: palette.bg, color: palette.fg }}
        >
          {BADGE_LABELS[state]}
        </span>
        {progressLabel ? <span className="small"> · {progressLabel}</span> : null}
      </div>
      {state === "failed" && status.processing_error ? (
        <div className="small" style={{ color: "var(--danger)" }}>
          {status.processing_error}
        </div>
      ) : null}
      {state === "partial" && status.processing_error ? (
        <div className="small" style={{ color: "var(--warning)" }}>
          {status.processing_error}
        </div>
      ) : null}
    </div>
  );
}

function renderProgressLabel(status: SourceProcessingStatus): string | null {
  if (status.processing_status === "queued") {
    return "Waiting to process";
  }
  if (status.pages_total > 0) {
    return `Processing ${status.pages_processed} of ${status.pages_total} pages`;
  }
  if (status.transcription_segments_count != null) {
    const dur = status.duration_seconds ? formatDuration(status.duration_seconds) : null;
    return dur
      ? `Transcribed · ${status.transcription_segments_count} segments · ${dur}`
      : `Transcribed · ${status.transcription_segments_count} segments`;
  }
  return null;
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}
