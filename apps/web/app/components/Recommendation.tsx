"use client";

import { useEffect, useState, type ReactNode } from "react";

/**
 * v2 'Calm' recommendation wrapper. Listens for the `mc-rec-loading` custom
 * event and shows a breathing italic-serif "thinking" line while a fresh
 * recommendation is being generated; falls through to children otherwise.
 *
 * Matches /ui-update/Mission Control v2 - Calm.html line 701. The breathe
 * keyframe is defined globally in globals.css.
 *
 * To trigger the loading state from elsewhere:
 *   window.dispatchEvent(new CustomEvent('mc-rec-loading', { detail: true }));
 */
export function Recommendation({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    function onEvent(e: Event) {
      const detail = (e as CustomEvent<boolean>).detail;
      setLoading(Boolean(detail));
    }
    window.addEventListener("mc-rec-loading", onEvent);
    return () => window.removeEventListener("mc-rec-loading", onEvent);
  }, []);

  if (loading) {
    return (
      <div
        className="serif"
        style={{
          animation: "breathe 1.6s ease-in-out infinite",
          fontStyle: "italic",
          fontSize: 18,
          color: "var(--ink-soft)",
          padding: "20px 0",
        }}
      >
        Thinking through what you should do next…
      </div>
    );
  }

  return <>{children}</>;
}
