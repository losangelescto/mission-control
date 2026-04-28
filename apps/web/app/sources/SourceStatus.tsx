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

const BADGE_STYLES: Record<SourceProcessingState, { bg: string; fg: string }> = {
  queued: { bg: "#e5e7eb", fg: "#374151" },
  processing: { bg: "#dbeafe", fg: "#1e40af" },
  partial: { bg: "#fef3c7", fg: "#92400e" },
  complete: { bg: "#d1fae5", fg: "#065f46" },
  failed: { bg: "#fee2e2", fg: "#991b1b" },
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
        <div className="small" style={{ color: "#991b1b" }}>
          {status.processing_error}
        </div>
      ) : null}
      {state === "partial" && status.processing_error ? (
        <div className="small" style={{ color: "#92400e" }}>
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
