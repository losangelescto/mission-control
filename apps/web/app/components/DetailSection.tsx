import type { ReactNode } from "react";

/**
 * v2 'Calm' detail section. Used inside long-form panels (task detail,
 * canon-change article, etc.) to break content into labeled blocks: a
 * 16px uppercase letterspaced h3 over flowing content.
 *
 * Matches /ui-update/Mission Control v2 - Calm.html line 689.
 */
export function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section style={{ marginBottom: 28 }}>
      <h3
        style={{
          fontFamily: "inherit",
          fontSize: 16,
          fontWeight: 600,
          margin: "0 0 12px",
          color: "var(--ink-soft)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        {title}
      </h3>
      {children}
    </section>
  );
}
