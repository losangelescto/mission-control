import Link from "next/link";
import type { CSSProperties, MouseEvent, ReactNode } from "react";

type BigButtonKind = "primary" | "secondary" | "quiet" | "danger";

const kindStyle: Record<BigButtonKind, CSSProperties> = {
  primary: {
    background: "var(--brass)",
    color: "var(--canvas)",
    borderColor: "var(--brass)",
  },
  secondary: {
    background: "transparent",
    color: "var(--ink)",
    borderColor: "var(--line-strong)",
  },
  quiet: {
    background: "transparent",
    color: "var(--ink-soft)",
    borderColor: "transparent",
  },
  danger: {
    background: "transparent",
    color: "var(--danger)",
    borderColor: "var(--danger)",
  },
};

const baseStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  height: 46,
  padding: "0 22px",
  fontSize: 15,
  fontWeight: 500,
  letterSpacing: "0.01em",
  border: "1px solid",
  borderRadius: 3,
  cursor: "pointer",
  textDecoration: "none",
  transition: "transform 80ms ease, background-color 120ms ease, color 120ms ease",
};

/**
 * v2 'Calm' button. Geometry matches /ui-update/Mission Control v2 - Calm.html
 * line 170: 46px height, 1px border, 3px radius, four kinds spaced by their
 * border + fill treatment.
 *
 * Renders as a Next <Link> when `href` is set, otherwise as a <button>. Either
 * shape stays a server component — no client-side hover handlers; CSS owns
 * hover via the .big-button class.
 */
export function BigButton({
  children,
  kind = "primary",
  full,
  href,
  type,
  onClick,
  disabled,
  ariaLabel,
}: {
  children: ReactNode;
  kind?: BigButtonKind;
  full?: boolean;
  href?: string;
  type?: "button" | "submit" | "reset";
  onClick?: (e: MouseEvent<HTMLButtonElement | HTMLAnchorElement>) => void;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  const style = {
    ...baseStyle,
    ...kindStyle[kind],
    width: full ? "100%" : undefined,
    opacity: disabled ? 0.55 : undefined,
    pointerEvents: disabled ? "none" as const : undefined,
  };

  if (href) {
    return (
      <Link
        href={href}
        className={`big-button big-button-${kind}`}
        aria-label={ariaLabel}
        onClick={onClick}
        style={style}
      >
        {children}
      </Link>
    );
  }

  return (
    <button
      type={type ?? "button"}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={`big-button big-button-${kind}`}
      style={style}
    >
      {children}
    </button>
  );
}
