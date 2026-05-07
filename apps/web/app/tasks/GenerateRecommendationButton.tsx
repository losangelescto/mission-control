"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BigButton } from "@/app/components/BigButton";
import { apiClient } from "@/lib/api/client";

type Props = {
  taskId: number;
  /** Reword the button when the panel is shown alongside an existing
   *  recommendation (the "Regenerate Analysis" CTA on unblock mode). */
  label?: string;
};

// Not just spinning — the hint text turns the wait into a feature: the model
// is reasoning over canon, task context, and resolved obstacles, not returning
// a cached lookup. Keep this in sync with the API's typical Anthropic latency.
const TYPICAL_LATENCY_TEXT =
  "Anthropic is reasoning over canon, task context, and resolved obstacles. Typical response time: 10–20 seconds.";

export default function GenerateRecommendationButton({
  taskId,
  label = "Generate recommendation",
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
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
      <span data-testid="generate-recommendation-wrapper">
        <BigButton
          kind="secondary"
          onClick={onClick}
          disabled={isGenerating}
          ariaLabel={label}
        >
          {isGenerating ? (
            <>
              <SpinnerIcon />
              Generating…
            </>
          ) : (
            <span data-testid="generate-recommendation">{label}</span>
          )}
        </BigButton>
      </span>
      {isGenerating ? (
        <p
          style={{ fontSize: 14, color: "var(--ink-faint)", fontStyle: "italic", margin: 0 }}
          aria-live="polite"
        >
          {TYPICAL_LATENCY_TEXT}
        </p>
      ) : null}
      {error ? (
        <p style={{ fontSize: 14, color: "var(--danger)", margin: 0 }} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function SpinnerIcon() {
  // Inline SVG so we don't pull in a new icon dependency. The CSS `spin`
  // keyframe is defined in globals.css.
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
        animation: "spin 0.9s linear infinite",
      }}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
