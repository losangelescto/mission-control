"use client";

import { useRouter, useSearchParams } from "next/navigation";

const SCOPES = [
  { value: "company", label: "Company" },
  { value: "community", label: "Community" },
  { value: "team", label: "Team" },
  { value: "person", label: "Person" },
];

export function ScopeSelector({ owners }: { owners: string[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentScope = searchParams.get("scope") ?? "company";
  const currentScopeId = searchParams.get("scope_id") ?? "";

  function onScopeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value;
    router.push(`/metrics?scope=${next}`);
  }

  function onScopeIdChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value;
    router.push(`/metrics?scope=${currentScope}&scope_id=${id}`);
  }

  const needsSecondary = currentScope === "person" || currentScope === "team" || currentScope === "community";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
      <span className="small" style={{ fontWeight: 600 }}>Scope:</span>
      <select
        value={currentScope}
        onChange={onScopeChange}
        style={{ width: "auto", height: "auto", padding: "0.25rem 0.5rem", fontSize: "0.9375rem" }}
      >
        {SCOPES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      {needsSecondary && currentScope === "person" && owners.length > 0 && (
        <>
          <span className="small" style={{ fontWeight: 600 }}>Person:</span>
          <select
            value={currentScopeId}
            onChange={onScopeIdChange}
            style={{ width: "auto", height: "auto", padding: "0.25rem 0.5rem", fontSize: "0.9375rem" }}
          >
            <option value="">All</option>
            {owners.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </>
      )}
      {needsSecondary && currentScope !== "person" && (
        <>
          <span className="small" style={{ fontWeight: 600 }}>{currentScope === "team" ? "Team:" : "Community:"}</span>
          <input
            type="text"
            placeholder={`Enter ${currentScope} name...`}
            defaultValue={currentScopeId}
            onBlur={(e) => {
              const id = e.target.value.trim();
              if (id !== currentScopeId) {
                router.push(`/metrics?scope=${currentScope}&scope_id=${id}`);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const id = (e.target as HTMLInputElement).value.trim();
                router.push(`/metrics?scope=${currentScope}&scope_id=${id}`);
              }
            }}
            style={{ width: "auto", height: "auto", padding: "0.25rem 0.5rem", fontSize: "0.9375rem", maxWidth: "200px" }}
          />
        </>
      )}
    </div>
  );
}
