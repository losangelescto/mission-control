"use client";

import type { ChangeEvent, ReactNode } from "react";

/**
 * v2 'Calm' checkbox. Native <input type="checkbox"> at 22×22 with
 * accent-color: var(--brass) — the spec rule "native form controls stay
 * native" applies; this is a thin styling wrapper, not a custom control.
 *
 * Matches /ui-update/Mission Control v2 - Calm.html line 232.
 *
 * Renders as a controlled checkbox when `checked`+`onChange` are provided,
 * uncontrolled when `defaultChecked` is provided.
 */
export function BigCheckbox({
  checked,
  defaultChecked,
  onChange,
  label,
  disabled,
  name,
}: {
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
  label: ReactNode;
  disabled?: boolean;
  name?: string;
}) {
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 12,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        defaultChecked={defaultChecked}
        onChange={onChange}
        disabled={disabled}
        name={name}
        style={{
          accentColor: "var(--brass)",
          width: 22,
          height: 22,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      />
      <span style={{ fontSize: 17, lineHeight: 1.4 }}>{label}</span>
    </label>
  );
}
