import { apiClient } from "@/lib/api/client";
import { parsePositiveIntParam } from "@/lib/search-params";
import Link from "next/link";

type SourcesPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * Strip a leading 32-char hex hash + underscore from a filename.
 * e.g. "63e290c31c3744e28a6d0144a6a15dc9_D00_Ecosystem.docx" → "D00_Ecosystem.docx"
 */
function displayName(filename: string): string {
  return filename.replace(/^[0-9a-f]{32}_/i, "");
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
                  {activeSet.has(source.id) ? <span className="badge">active canon</span> : null}
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
                Status:{" "}
                {selectedSource.is_active_canon_version ? (
                  <span className="badge">active canon</span>
                ) : selectedSource.source_type === "canon_doc" ? (
                  "inactive"
                ) : (
                  "-"
                )}
              </div>
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
