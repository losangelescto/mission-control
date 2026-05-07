"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Three close affordances for any detail panel that opens via a ?selected=
 * (or ?source_id= / ?event_id=) URL param:
 *   1. Top-right X button (aria-label="Close")
 *   2. Escape key handler
 *   3. The list row that selected this panel toggles deselect on re-click
 *      (handled at the row Link's href, not here)
 *
 * On close, navigates to `closeHref` — the page URL with the selection
 * param dropped but other filters preserved. Server re-renders the page
 * without the detail panel and the URL is clean.
 *
 * The parent article must be `position: relative` so the absolute X button
 * anchors to it.
 */
export function CloseDetailPanel({ closeHref }: { closeHref: string }) {
  const router = useRouter();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") router.push(closeHref);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeHref, router]);

  return (
    <button
      type="button"
      onClick={() => router.push(closeHref)}
      aria-label="Close"
      data-testid="close-detail-panel"
      style={{
        position: "absolute",
        top: 16,
        right: 16,
        width: 32,
        height: 32,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "transparent",
        border: "1px solid var(--line)",
        borderRadius: 3,
        color: "var(--ink-soft)",
        cursor: "pointer",
        fontSize: 18,
        lineHeight: 1,
        transition: "color 120ms ease, border-color 120ms ease",
      }}
    >
      <span aria-hidden="true">×</span>
    </button>
  );
}
