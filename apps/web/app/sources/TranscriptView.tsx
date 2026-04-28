import type { TranscriptionSegment } from "@/lib/api/types";

type Props = {
  segments: TranscriptionSegment[];
  durationSeconds?: number;
};

export default function TranscriptView({ segments, durationSeconds }: Props) {
  if (segments.length === 0) {
    return <p className="small">No transcript segments available.</p>;
  }
  return (
    <details>
      <summary>
        Transcript · {segments.length} segments
        {durationSeconds ? ` · ${formatDuration(durationSeconds)}` : ""}
      </summary>
      <div className="stack-sm" style={{ marginTop: "0.5rem" }}>
        {segments.map((seg, idx) => (
          <div key={idx}>
            <div className="small mono">
              [{formatTimestamp(seg.start_time)} → {formatTimestamp(seg.end_time)}]{" "}
              <strong>{seg.speaker}</strong>
            </div>
            <div className="small">{seg.text}</div>
          </div>
        ))}
      </div>
    </details>
  );
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}
