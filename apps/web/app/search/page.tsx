import Link from "next/link";

import { apiClient } from "@/lib/api/client";
import { firstSearchParam } from "@/lib/search-params";
import type { SearchMode, SearchResponse, SearchTypeFilter } from "@/lib/api/types";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const TYPE_FILTERS: { key: SearchTypeFilter; label: string; counts: string[] }[] = [
  { key: "all", label: "All", counts: [] },
  { key: "tasks", label: "Tasks", counts: ["tasks", "task_updates", "sub_tasks", "obstacles"] },
  { key: "sources", label: "Sources", counts: ["sources"] },
  { key: "reviews", label: "Reviews", counts: ["reviews"] },
  { key: "canon", label: "Canon", counts: ["canon"] },
];

const PAGE_SIZE = 20;

function buildHref(
  q: string,
  type: SearchTypeFilter,
  mode: SearchMode,
  page: number,
): string {
  const params = new URLSearchParams({ q });
  if (type !== "all") params.set("type", type);
  if (mode !== "keyword") params.set("mode", mode);
  if (page > 1) params.set("page", String(page));
  return `/search?${params.toString()}`;
}

function sumCounts(counts: Record<string, number>, keys: string[]): number {
  if (keys.length === 0) {
    return Object.values(counts).reduce((a, b) => a + b, 0);
  }
  return keys.reduce((a, k) => a + (counts[k] ?? 0), 0);
}

export default async function SearchPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const q = firstSearchParam(params.q) ?? "";
  const typeRaw = firstSearchParam(params.type) ?? "all";
  const modeRaw = firstSearchParam(params.mode) ?? "keyword";
  const pageRaw = firstSearchParam(params.page);

  const type: SearchTypeFilter = (
    ["all", "tasks", "sources", "reviews", "canon"] as const
  ).includes(typeRaw as SearchTypeFilter)
    ? (typeRaw as SearchTypeFilter)
    : "all";
  const mode: SearchMode = modeRaw === "semantic" ? "semantic" : "keyword";
  const page = Math.max(1, Number.parseInt(pageRaw ?? "1", 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  let response: SearchResponse | null = null;
  let error: string | null = null;
  if (q.trim().length > 0) {
    try {
      response = await apiClient.search(q, {
        type,
        mode,
        limit: PAGE_SIZE,
        offset,
      });
    } catch (e) {
      error = e instanceof Error ? e.message : "Search failed.";
    }
  }

  const totalPages = response ? Math.max(1, Math.ceil(response.total / PAGE_SIZE)) : 1;

  return (
    <section className="stack">
      <div className="panel">
        <h1>Search</h1>
        <form method="get" action="/search" className="stack-sm">
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="Search tasks, sources, reviews, canon…"
            aria-label="Search query"
            style={{ width: "100%", padding: "0.5rem", fontSize: "1rem" }}
          />
          <input type="hidden" name="type" value={type} />
          <input type="hidden" name="mode" value={mode} />
        </form>
        <div className="meta-row" style={{ marginTop: "0.5rem", flexWrap: "wrap", gap: "0.4rem" }}>
          {(["keyword", "semantic"] as const).map((m) => (
            <Link
              key={m}
              href={buildHref(q, type, m, 1)}
              className={mode === m ? "badge" : "small"}
              aria-current={mode === m ? "true" : undefined}
            >
              {m === "keyword" ? "Keyword" : "Semantic"}
            </Link>
          ))}
        </div>
      </div>

      {q.trim().length === 0 ? (
        <article className="panel">
          <p className="small">Enter a query above to search.</p>
        </article>
      ) : error ? (
        <article className="panel">
          <p className="small" style={{ color: "#991b1b" }}>{error}</p>
        </article>
      ) : (
        <div className="grid cols-2" style={{ gridTemplateColumns: "200px 1fr" }}>
          <aside className="panel">
            <h3>Filter</h3>
            <ul className="list">
              {TYPE_FILTERS.map((f) => {
                const count = response ? sumCounts(response.type_counts, f.counts) : 0;
                const active = f.key === type;
                return (
                  <li key={f.key}>
                    <Link
                      href={buildHref(q, f.key, mode, 1)}
                      style={{ fontWeight: active ? 600 : 400 }}
                      aria-current={active ? "true" : undefined}
                    >
                      {f.label}
                      {response ? ` (${count})` : ""}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </aside>

          <article className="panel">
            <h2>
              {response ? `${response.total} result${response.total === 1 ? "" : "s"}` : "Searching…"}
              {response && mode === "semantic" ? <span className="badge" style={{ marginLeft: "0.5rem" }}>semantic</span> : null}
            </h2>
            {response && response.results.length === 0 ? (
              <p className="small">No matches for that query.</p>
            ) : null}
            <ul className="list">
              {response?.results.map((r) => (
                <li key={`${r.type}-${r.id}-${r.url}`}>
                  <div>
                    <Link href={r.url}>
                      <strong>{r.title}</strong>
                    </Link>{" "}
                    <span className="badge">{r.type.replace("_", " ")}</span>
                  </div>
                  <div
                    className="small"
                    style={{ marginTop: "0.25rem" }}
                    dangerouslySetInnerHTML={{ __html: r.snippet }}
                  />
                </li>
              ))}
            </ul>
            {response && totalPages > 1 ? (
              <div className="meta-row" style={{ marginTop: "0.75rem", justifyContent: "space-between" }}>
                <span className="small">
                  Page {page} of {totalPages}
                </span>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  {page > 1 ? (
                    <Link href={buildHref(q, type, mode, page - 1)}>← Prev</Link>
                  ) : null}
                  {page < totalPages ? (
                    <Link href={buildHref(q, type, mode, page + 1)}>Next →</Link>
                  ) : null}
                </div>
              </div>
            ) : null}
          </article>
        </div>
      )}
    </section>
  );
}
