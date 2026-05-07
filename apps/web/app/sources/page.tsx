import Link from "next/link";

import { CloseDetailPanel } from "@/app/components/CloseDetailPanel";
import { DetailSection } from "@/app/components/DetailSection";
import { PageTitle } from "@/app/components/PageTitle";
import { apiClient } from "@/lib/api/client";
import { parsePositiveIntParam } from "@/lib/search-params";

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

const SOURCE_TYPE_LABEL: Record<string, string> = {
  canon_doc: "Canon document",
  thread_export: "Thread export",
  transcript: "Recorded call",
  note: "Note",
  board_seed: "Board seed",
};

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

function formatAdded(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
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

  const subtitle =
    sources.length === 0
      ? "Documents drive everything here. Uploaded sources are read by the system to extract tasks and canon."
      : sources.length === 1
        ? "One source uploaded so far."
        : `${sources.length} sources uploaded. Click one to inspect what was extracted.`;

  return (
    <div style={{ maxWidth: 980 }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 24,
          flexWrap: "wrap",
          marginBottom: 16,
        }}
      >
        <PageTitle sub={subtitle}>Sources</PageTitle>
        <UploadSource />
      </div>

      {/* Source list — single column of v2 doc-row cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 40 }}>
        {sources.length === 0 ? (
          <div
            style={{
              padding: "32px 28px",
              border: "2px solid var(--line)",
              borderRadius: 8,
              background: "var(--surface)",
              textAlign: "center",
              color: "var(--ink-soft)",
              fontStyle: "italic",
              fontSize: 16,
            }}
          >
            No sources uploaded yet.
          </div>
        ) : (
          sources.map((source) => {
            const isSelected = source.id === sourceId;
            const isActiveCanon = activeSet.has(source.id);
            const kindLabel =
              SOURCE_TYPE_LABEL[source.source_type] ?? source.source_type;
            return (
              <Link
                key={source.id}
                href={isSelected ? "/sources" : `/sources?source_id=${source.id}`}
                className="task-list-row"
                data-selected={isSelected ? "true" : undefined}
                aria-pressed={isSelected}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 18,
                  padding: "20px 24px",
                  background: isSelected ? "var(--surface-raised)" : "var(--surface)",
                  border: "2px solid",
                  borderColor: isSelected ? "var(--brass)" : "var(--line)",
                  borderRadius: 8,
                  textDecoration: "none",
                  color: "inherit",
                  transition: "border-color 120ms ease, background 120ms ease",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 18,
                      fontWeight: 500,
                      lineHeight: 1.35,
                      marginBottom: 6,
                      color: "var(--ink)",
                    }}
                  >
                    {sourceLabel(source)}
                  </div>
                  <div style={{ fontSize: 14, color: "var(--ink-soft)" }}>
                    {kindLabel}
                    {source.version_label ? <> · {source.version_label}</> : null}
                    {" · Added "}
                    {formatAdded(source.created_at)}
                  </div>
                </div>
                {isActiveCanon ? (
                  <span
                    style={{
                      padding: "6px 14px",
                      borderRadius: 999,
                      background: "color-mix(in oklch, var(--brass) 14%, transparent)",
                      color: "var(--brass-deep)",
                      fontSize: 13,
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                      whiteSpace: "nowrap",
                    }}
                  >
                    Active Canon
                  </span>
                ) : null}
              </Link>
            );
          })
        )}
      </div>

      {/* Selected source detail */}
      {selectedSource ? (
        <article
          style={{
            background: "var(--surface-raised)",
            border: "2px solid var(--line)",
            borderRadius: 10,
            padding: "32px 36px",
            marginBottom: 32,
            position: "relative",
          }}
        >
          <CloseDetailPanel closeHref="/sources" />
          <h2
            className="serif"
            style={{
              fontSize: 28,
              fontWeight: 400,
              letterSpacing: "-0.005em",
              lineHeight: 1.2,
              margin: "0 0 6px",
              color: "var(--ink)",
            }}
          >
            {sourceLabel(selectedSource)}
          </h2>
          {sourceLabel(selectedSource) !== displayName(selectedSource.filename) ? (
            <div style={{ fontSize: 14, color: "var(--ink-faint)", marginBottom: 18 }}>
              ({displayName(selectedSource.filename)})
            </div>
          ) : null}
          <div style={{ fontSize: 16, color: "var(--ink-soft)", marginBottom: 28 }}>
            {SOURCE_TYPE_LABEL[selectedSource.source_type] ?? selectedSource.source_type}
            {selectedSource.version_label ? <> · {selectedSource.version_label}</> : null}
            {" · ID #"}{selectedSource.id}
            {" · Added "}{formatAdded(selectedSource.created_at)}
          </div>

          {selectedStatus ? (
            <DetailSection title="Processing status">
              <SourceStatus sourceId={selectedSource.id} initial={selectedStatus} />
            </DetailSection>
          ) : null}

          <DetailSection title="Canon">
            {selectedSource.is_active_canon_version ? (
              <span
                style={{
                  padding: "6px 14px",
                  borderRadius: 999,
                  background: "color-mix(in oklch, var(--brass) 14%, transparent)",
                  color: "var(--brass-deep)",
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                }}
              >
                Active Canon
              </span>
            ) : selectedSource.source_type === "canon_doc" ? (
              <span style={{ fontSize: 15, color: "var(--ink-soft)" }}>Inactive version</span>
            ) : (
              <span style={{ fontSize: 15, color: "var(--ink-faint)" }}>Not a canon document</span>
            )}
            {selectedSource.canonical_doc_id ? (
              <div style={{ marginTop: 6, fontSize: 14, color: "var(--ink-faint)" }}>
                Canonical doc id: <code>{selectedSource.canonical_doc_id}</code>
              </div>
            ) : null}
          </DetailSection>

          {isMediaFile(selectedSource.filename) && selectedSource.processing_metadata ? (
            <DetailSection title="Transcript">
              <TranscriptView
                segments={selectedSource.processing_metadata.segments ?? []}
                durationSeconds={selectedSource.processing_metadata.duration_seconds}
              />
            </DetailSection>
          ) : null}

          <DetailSection title="Extracted text">
            <details>
              <summary style={{ fontSize: 15 }}>Show first 3000 characters</summary>
              <pre className="small mono" style={{ marginTop: 10 }}>
                {selectedSource.extracted_text.slice(0, 3000)}
              </pre>
            </details>
          </DetailSection>

          <DetailSection title="Danger zone">
            <DeleteSourceButton
              sourceId={selectedSource.id}
              sourceLabel={sourceLabel(selectedSource)}
              isActiveCanon={selectedSource.is_active_canon_version}
            />
          </DetailSection>
        </article>
      ) : null}
    </div>
  );
}
