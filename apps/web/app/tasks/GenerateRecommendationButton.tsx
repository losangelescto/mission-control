"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiClient } from "@/lib/api/client";

type Props = {
  taskId: number;
  /** Reword the button when the panel is shown alongside an existing
   *  recommendation (the "Regenerate Analysis" CTA on unblock mode). */
  label?: string;
};

// 16 -- not just spinning. The hint text turns the wait into a feature:
// the model is reasoning over canon, task context, and resolved obstacles,
// not returning a cached lookup. Keep this in sync with the API's typical
// Anthropic latency.
const TYPICAL_LATENCY_TEXT =
  "Anthropic is reasoning over canon, task context, and resolved obstacles. Typical response time: 10–20 seconds.";

export default function GenerateRecommendationButton({
  taskId,
  label = "Generate Recommendation",
}: Props) {
  const router = useRouter();
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    setError(null);
    setIsGenerating(true);
    try {
      await apiClient.generateRecommendation(taskId);
      // Re-fetch the server-rendered page so the new recommendation
      // (read via apiClient.getLatestRecommendation in the page) shows up
      // without a full reload. The button re-enables once the refresh
      // settles via the finally block below.
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Recommendation failed");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div className="stack-sm">
      <button
        type="button"
        className="link-btn"
        onClick={onClick}
        disabled={isGenerating}
        aria-busy={isGenerating}
        data-testid="generate-recommendation"
      >
        {isGenerating ? (
          <>
            <SpinnerIcon />
            Generating…
          </>
        ) : (
          label
        )}
      </button>
      {isGenerating ? (
        <p
          className="small"
          style={{ color: "var(--text-tertiary)", fontStyle: "italic" }}
          aria-live="polite"
        >
          {TYPICAL_LATENCY_TEXT}
        </p>
      ) : null}
      {error ? (
        <p className="small" role="alert" style={{ color: "#991b1b" }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function SpinnerIcon() {
  // Inline SVG so we don't pull in a new icon dependency. The CSS
  // animation keyframes used here (`spin`) are defined in globals.css.
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{
        marginRight: "0.4rem",
        animation: "spin 0.9s linear infinite",
      }}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
