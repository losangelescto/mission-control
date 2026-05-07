import type { ReactNode } from "react";

/**
 * v2 'Calm' page title. Three slots: optional uppercase eyebrow (brass,
 * letterspaced), serif h1, optional italic-serif subtitle. Used at the top
 * of every primary route.
 *
 * Dimensions / weights match /ui-update/Mission Control v2 - Calm.html line 136.
 */
export function PageTitle({
  eyebrow,
  children,
  sub,
}: {
  eyebrow?: ReactNode;
  children: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="page-title" style={{ marginBottom: 32 }}>
      {eyebrow ? (
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--brass)",
            marginBottom: 14,
          }}
        >
          {eyebrow}
        </div>
      ) : null}
      <h1
        className="serif"
        style={{
          fontWeight: 400,
          fontSize: 42,
          letterSpacing: "-0.015em",
          lineHeight: 1.08,
          margin: 0,
          color: "var(--ink)",
        }}
      >
        {children}
      </h1>
      {sub ? (
        <p
          className="serif"
          style={{
            fontStyle: "italic",
            fontSize: 18,
            lineHeight: 1.55,
            color: "var(--ink-soft)",
            margin: "14px 0 0",
            maxWidth: 640,
          }}
        >
          {sub}
        </p>
      ) : null}
    </div>
  );
}
