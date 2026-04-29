"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { apiClient } from "@/lib/api/client";
import type { SearchResponse, SearchResult, SearchResultType } from "@/lib/api/types";

const DEBOUNCE_MS = 300;
const MIN_QUERY = 3;
const PREVIEW_LIMIT = 8;

const TYPE_LABEL: Record<SearchResultType, string> = {
  task: "Task",
  task_update: "Update",
  sub_task: "Sub-task",
  obstacle: "Obstacle",
  source: "Source",
  source_chunk: "Source",
  review: "Review",
  canon: "Canon",
};

const TYPE_ICON: Record<SearchResultType, string> = {
  task: "▣",
  task_update: "▤",
  sub_task: "▢",
  obstacle: "▲",
  source: "▦",
  source_chunk: "▦",
  review: "✎",
  canon: "★",
};

const GROUP_ORDER: { key: string; types: SearchResultType[]; label: string }[] = [
  { key: "tasks", types: ["task", "task_update", "sub_task", "obstacle"], label: "Tasks" },
  { key: "sources", types: ["source", "source_chunk"], label: "Sources" },
  { key: "reviews", types: ["review"], label: "Reviews" },
  { key: "canon", types: ["canon"], label: "Canon" },
];

function groupResults(results: SearchResult[]) {
  const groups: { label: string; key: string; items: SearchResult[] }[] = [];
  for (const g of GROUP_ORDER) {
    const items = results.filter((r) => g.types.includes(r.type));
    if (items.length > 0) groups.push({ label: g.label, key: g.key, items });
  }
  return groups;
}

export default function SearchBar() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Cmd+K / Ctrl+K to focus the input.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isCmd = e.metaKey || e.ctrlKey;
      if (isCmd && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen(false);
        inputRef.current?.blur();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Click outside closes the dropdown.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  // Debounced fetch.
  useEffect(() => {
    if (query.trim().length < MIN_QUERY) {
      setData(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await apiClient.search(query, {
          limit: PREVIEW_LIMIT,
          signal: controller.signal,
        });
        setData(res);
      } catch (err) {
        if ((err as { name?: string })?.name !== "AbortError") {
          setData(null);
        }
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  function submitFullSearch() {
    const trimmed = query.trim();
    if (!trimmed) return;
    setOpen(false);
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  function onResultClick(url: string) {
    setOpen(false);
    router.push(url);
  }

  const grouped = data ? groupResults(data.results) : [];
  const showDropdown = open && query.trim().length >= MIN_QUERY;

  return (
    <div ref={containerRef} className="search-bar" style={{ position: "relative", flex: 1, maxWidth: "32rem" }}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitFullSearch();
        }}
      >
        <input
          ref={inputRef}
          type="search"
          placeholder="Search… (⌘K)"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          aria-label="Search Mission Control"
          aria-autocomplete="list"
          aria-expanded={showDropdown}
          style={{
            width: "100%",
            padding: "0.4rem 0.6rem",
            borderRadius: "6px",
            border: "1px solid var(--border, #d1d5db)",
            background: "var(--bg, #fff)",
            color: "inherit",
            fontFamily: "inherit",
            fontSize: "0.85rem",
          }}
        />
      </form>

      {showDropdown ? (
        <div
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            zIndex: 50,
            maxHeight: "60vh",
            overflowY: "auto",
            background: "var(--panel, #fff)",
            border: "1px solid var(--border, #d1d5db)",
            borderRadius: "6px",
            boxShadow: "0 6px 24px rgba(0,0,0,0.18)",
          }}
        >
          {loading && !data ? (
            <div className="small" style={{ padding: "0.6rem" }}>
              Searching…
            </div>
          ) : null}
          {!loading && data && data.results.length === 0 ? (
            <div className="small" style={{ padding: "0.6rem" }}>
              No matches.
            </div>
          ) : null}
          {grouped.map((group) => (
            <div key={group.key}>
              <div
                className="small"
                style={{
                  padding: "0.35rem 0.6rem",
                  background: "var(--panel-alt, #f3f4f6)",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                {group.label}
              </div>
              {group.items.map((r) => (
                <button
                  key={`${r.type}-${r.id}-${r.url}`}
                  type="button"
                  onClick={() => onResultClick(r.url)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "0.5rem 0.6rem",
                    background: "transparent",
                    border: "none",
                    borderTop: "1px solid var(--border-subtle, #e5e7eb)",
                    cursor: "pointer",
                    color: "inherit",
                  }}
                >
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
                    <span aria-hidden="true">{TYPE_ICON[r.type]}</span>
                    <strong style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {r.title}
                    </strong>
                    <span className="badge">{TYPE_LABEL[r.type]}</span>
                  </div>
                  <div
                    className="small"
                    style={{ marginTop: "0.2rem" }}
                    dangerouslySetInnerHTML={{ __html: r.snippet }}
                  />
                </button>
              ))}
            </div>
          ))}
          <div
            style={{
              borderTop: "1px solid var(--border-subtle, #e5e7eb)",
              padding: "0.4rem 0.6rem",
              textAlign: "right",
            }}
          >
            <Link
              href={`/search?q=${encodeURIComponent(query)}`}
              onClick={() => setOpen(false)}
              className="small"
            >
              See all results{data ? ` (${data.total})` : ""} →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
