"use client";

import { useEffect, useState } from "react";

import {
  formatIsoForLocal,
  formatIsoForSsr,
  type TimeFormat,
} from "@/lib/time-display";

// Renders an ISO timestamp deterministically across SSR and first client
// render (always UTC), then upgrades to the user's local timezone after
// mount. This is the cure for React #418 caused by toLocaleString picking
// up different zones on Node (UTC) vs the browser (user-local).
export function TimeDisplay({
  iso,
  format = "datetime",
  className,
}: {
  iso: string;
  format?: TimeFormat;
  className?: string;
}) {
  const [text, setText] = useState(() => formatIsoForSsr(iso, format));
  useEffect(() => {
    setText(formatIsoForLocal(iso, format));
  }, [iso, format]);
  return (
    <span className={className} suppressHydrationWarning>
      {text}
    </span>
  );
}
