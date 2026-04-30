import { apiClient } from "@/lib/api/client";
import { parsePositiveIntParam } from "@/lib/search-params";
import Link from "next/link";

import DeleteSourceButton from "./DeleteSourceButton";
import SourceStatus from "./SourceStatus";
import TranscriptView from "./TranscriptView";
import UploadSource from "./UploadSource";

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

// Prefer the user-supplied title (stored in processing_metadata.title at
// upload time) over the raw filename so the source list reads naturally.
function sourceLabel(source: { filename: string; processing_metadata?: Record<string, unknown> | null }): string {
  const meta = source.processing_metadata;
  const title = meta && typeof meta.title === "string" ? meta.title.trim() : "";
  return title || displayName(source.filename);
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
  // Only honour an explicit ?source_id= in the URL. The previous auto-pick
  // of sources[0] flashed the next source's detail (and its delete-confirm
  // modal binding) into the panel right after a force-delete redirected
  // back here without a selection. Empty selection now means empty panel.
  const selectedSource =
    sourceId != null ? await apiClient.getSource(sourceId).catch(() => null) : null;

  const selectedStatus = selectedSource
    ? await apiClient.getSourceStatus(selectedSource.id).catch(() => null)
    : null;

  return (
    <section className="stack">
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem" }}>
          <h1>Sources</h1>
          <UploadSource />
        </div>
        <form action="/search" method="get" className="stack-sm" style={{ marginTop: "0.5rem" }}>
          <input
            type="search"
            name="q"
            placeholder="Search sources by filename or text…"
            aria-label="Search within sources"
            style={{ width: "100%", padding: "0.4rem 0.6rem" }}
          />
          <input type="hidden" name="type" value="sources" />
        </form>
      </div>
      <div className="grid cols-2">
        <article className="panel">
          <h2>Source List</h2>
          <ul className="list">
            {sources.map((source) => (
              <li key={source.id}>
                <div>
                  <Link href={`/sources?source_id=${source.id}`}>
                    <strong>{sourceLabel(source)}</strong>
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
                <strong>{sourceLabel(selectedSource)}</strong>
                {sourceLabel(selectedSource) !== displayName(selectedSource.filename) ? (
                  <span className="small" style={{ marginLeft: "0.5rem", color: "var(--text-tertiary)" }}>
                    ({displayName(selectedSource.filename)})
                  </span>
                ) : null}
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
              <div style={{ marginTop: "0.5rem" }}>
                <DeleteSourceButton
                  sourceId={selectedSource.id}
                  sourceLabel={sourceLabel(selectedSource)}
                  isActiveCanon={selectedSource.is_active_canon_version}
                />
              </div>
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
