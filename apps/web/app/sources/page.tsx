import { apiClient } from "@/lib/api/client";
import { parsePositiveIntParam } from "@/lib/search-params";
import Link from "next/link";

import SourceStatus from "./SourceStatus";
import TranscriptView from "./TranscriptView";

type SourcesPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const AUDIO_VIDEO_EXTENSIONS = [
  ".mp3",
  ".wav",
  ".m4a",
  ".ogg",
  ".flac",
  ".mp4",
  ".webm",
  ".mov",
];

function displayName(filename: string): string {
  return filename.replace(/^[0-9a-f]{32}_/i, "");
}

function isMediaFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return AUDIO_VIDEO_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default async function SourcesPage({ searchParams }: SourcesPageProps) {
  const params = await searchParams;
  const sourceId = parsePositiveIntParam(params.source_id) ?? null;

  const [sources, activeCanon] = await Promise.all([
    apiClient.getSources(),
    apiClient.getActiveCanon(),
  ]);
  const activeSet = new Set(activeCanon.map((doc) => doc.id));
  const selectedSource =
    sourceId != null
      ? await apiClient.getSource(sourceId).catch(() => null)
      : sources.length > 0
        ? sources[0]
        : null;

  const selectedStatus = selectedSource
    ? await apiClient.getSourceStatus(selectedSource.id).catch(() => null)
    : null;

  return (
    <section className="stack">
      <div className="panel">
        <h1>Sources</h1>
      </div>
      <div className="grid cols-2">
        <article className="panel">
          <h2>Source List</h2>
          <ul className="list">
            {sources.map((source) => (
              <li key={source.id}>
                <div>
                  <Link href={`/sources?source_id=${source.id}`}>
                    <strong>{displayName(source.filename)}</strong>
                  </Link>
                </div>
                <div className="small">
                  {source.source_type}{" "}
                  {activeSet.has(source.id) ? <span className="badge">active canon</span> : null}{" "}
                  <span className="badge" style={statusBadgeStyle(source.processing_status)}>
                    {source.processing_status}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </article>
        <article className="panel">
          <h2>Source Detail</h2>
          {selectedSource ? (
            <div className="stack-sm">
              <div>
                <strong>{displayName(selectedSource.filename)}</strong>
              </div>
              <div className="small">ID: {selectedSource.id}</div>
              <div className="small">Type: {selectedSource.source_type}</div>
              <div className="small">Canonical Doc ID: {selectedSource.canonical_doc_id ?? "-"}</div>
              <div className="small">Version: {selectedSource.version_label ?? "-"}</div>
              <div className="small">
                Canon:{" "}
                {selectedSource.is_active_canon_version ? (
                  <span className="badge">active canon</span>
                ) : selectedSource.source_type === "canon_doc" ? (
                  "inactive"
                ) : (
                  "-"
                )}
              </div>
              {selectedStatus ? (
                <SourceStatus sourceId={selectedSource.id} initial={selectedStatus} />
              ) : null}
              {isMediaFile(selectedSource.filename) && selectedSource.processing_metadata ? (
                <TranscriptView
                  segments={selectedSource.processing_metadata.segments ?? []}
                  durationSeconds={selectedSource.processing_metadata.duration_seconds}
                />
              ) : null}
              <details>
                <summary>Extracted Text</summary>
                <pre className="small mono">{selectedSource.extracted_text.slice(0, 3000)}</pre>
              </details>
            </div>
          ) : (
            <p className="small">No source selected.</p>
          )}
        </article>
      </div>
    </section>
  );
}

function statusBadgeStyle(state: string): { background: string; color: string } {
  switch (state) {
    case "queued":
      return { background: "#e5e7eb", color: "#374151" };
    case "processing":
      return { background: "#dbeafe", color: "#1e40af" };
    case "partial":
      return { background: "#fef3c7", color: "#92400e" };
    case "failed":
      return { background: "#fee2e2", color: "#991b1b" };
    default:
      return { background: "#d1fae5", color: "#065f46" };
  }
}
