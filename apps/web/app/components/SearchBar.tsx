"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { apiClient } from "@/lib/api/client";
import type { SearchResponse } from "@/lib/api/types";
import {
  TYPE_ICON,
  TYPE_LABEL,
  groupSearchResults,
} from "@/lib/search-grouping";
import { HYPHEN_HINT_TEXT, shouldShowHyphenHint } from "@/lib/search-hint";

const DEBOUNCE_MS = 300;
const MIN_QUERY = 3;
const PREVIEW_LIMIT = 8;

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

  const grouped = groupSearchResults(data?.results);
  const showDropdown = open && query.trim().length >= MIN_QUERY;
  const hasResults = grouped.length > 0;

  return (
    <div
      ref={containerRef}
      className="search-bar"
      style={{ position: "relative", flex: 1, maxWidth: "32rem" }}
    >
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
            border: "1px solid var(--border)",
            background: "var(--bg-input)",
            color: "inherit",
            fontFamily: "inherit",
            fontSize: "0.85rem",
          }}
        />
      </form>

      {showDropdown ? (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            zIndex: 50,
            maxHeight: "60vh",
            overflowY: "auto",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            boxShadow: "0 6px 24px rgba(0,0,0,0.18)",
          }}
          data-testid="search-dropdown"
        >
          {loading && !data ? (
            <div className="small" style={{ padding: "0.6rem" }}>
              Searching…
            </div>
          ) : null}
          {!loading && data && !hasResults ? (
            <div className="small" style={{ padding: "0.6rem" }}>
              {shouldShowHyphenHint(query, hasResults) ? HYPHEN_HINT_TEXT : "No matches."}
            </div>
          ) : null}

          {hasResults ? (
            <ul
              role="listbox"
              aria-label="Search results"
              style={{ listStyle: "none", margin: 0, padding: 0 }}
            >
              {grouped.map((group) => (
                <li key={group.key} role="presentation" data-testid={`search-group-${group.key}`}>
                  <div
                    className="small"
                    style={{
                      padding: "0.35rem 0.6rem",
                      background: "var(--bg-surface)",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {group.label}
                  </div>
                  <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                    {group.items.map((r) => (
                      <li
                        key={`${r.type}-${r.id}-${r.url}`}
                        role="option"
                        aria-selected="false"
                        data-testid={`search-result-${r.type}-${r.id}`}
                        style={{
                          borderTop: "1px solid var(--border)",
                        }}
                      >
                        <button
                          type="button"
                          onClick={() => onResultClick(r.url)}
                          style={{
                            display: "flex",
                            width: "100%",
                            gap: "0.5rem",
                            alignItems: "baseline",
                            padding: "0.5rem 0.6rem 0.1rem",
                            background: "transparent",
                            border: "none",
                            textAlign: "left",
                            cursor: "pointer",
                            color: "inherit",
                            font: "inherit",
                          }}
                        >
                          <span aria-hidden="true">{TYPE_ICON[r.type]}</span>
                          <strong
                            style={{
                              flex: 1,
                              minWidth: 0,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {r.title}
                          </strong>
                          <span className="badge">{TYPE_LABEL[r.type]}</span>
                        </button>
                        {/*
                          Snippet rendered OUTSIDE the button. The previous
                          structure put a <div dangerouslySetInnerHTML> inside
                          the <button>, which left the row visually empty in
                          some browsers under React strict-mode hydration.
                          Sibling div + clickable wrapper avoids the issue.
                        */}
                        <div
                          onClick={() => onResultClick(r.url)}
                          className="small"
                          style={{
                            padding: "0 0.6rem 0.5rem 1.6rem",
                            cursor: "pointer",
                            color: "var(--text-tertiary)",
                          }}
                          dangerouslySetInnerHTML={{ __html: r.snippet || "" }}
                        />
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : null}

          <div
            style={{
              borderTop: "1px solid var(--border)",
              padding: "0.4rem 0.6rem",
              textAlign: "right",
            }}
          >
            <Link
              href={`/search?q=${encodeURIComponent(query)}`}
              onClick={() => setOpen(false)}
              className="small"
              data-testid="search-see-all"
            >
              See all results{data ? ` (${data.total})` : ""} →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
