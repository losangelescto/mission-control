"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { BigButton } from "@/app/components/BigButton";
import type { SourceType } from "@/lib/api/types";
import { resolveSourceTypeAfterFilePick } from "@/lib/upload-source";

const SOURCE_TYPES: readonly SourceType[] = [
  "canon_doc",
  "thread_export",
  "transcript",
  "note",
  "board_seed",
];

const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  canon_doc: "Canon document",
  thread_export: "Thread export",
  transcript: "Recorded call",
  note: "Note",
  board_seed: "Board seed",
};

const ACCEPT_EXTENSIONS =
  ".pdf,.txt,.md,.docx,.mp3,.mp4,.m4a,.wav,.ogg,.flac,.webm,.mov";

const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(15, 13, 10, 0.4)",
  backdropFilter: "blur(2px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
  padding: "1rem",
};

const PANEL: React.CSSProperties = {
  background: "var(--surface-raised)",
  color: "var(--ink)",
  borderRadius: 10,
  border: "2px solid var(--line)",
  padding: "28px 30px",
  width: "100%",
  maxWidth: "34rem",
  boxShadow: "var(--shadow-md)",
  maxHeight: "90vh",
  overflowY: "auto",
};

export default function UploadSource() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chosenName, setChosenName] = useState<string>("");
  const [sourceType, setSourceType] = useState<SourceType>("note");
  // Track whether the user has explicitly chosen a source type so we never
  // overwrite their selection with a filename-derived inference. Without
  // this, picking a file after manually selecting "canon_doc" used to flip
  // sourceType back, which in turn unmounted the canon-specific section
  // and dropped the Activate-checkbox state silently.
  const [sourceTypeUserSet, setSourceTypeUserSet] = useState(false);
  // Activate toggle is fully controlled — the previous uncontrolled
  // checkbox lost its visual state when the canon block remounted on a
  // source-type flip even though the user had ticked it. Holding the
  // value in state keeps visual + submitted value aligned at all times.
  const [activate, setActivate] = useState(false);

  // Esc closes (matches BlockTaskDialog pattern).
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) closeDialog();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy]);

  // Lock body scroll while open.
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  function closeDialog() {
    setOpen(false);
    setError(null);
    setChosenName("");
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) {
      setChosenName("");
      return;
    }
    setChosenName(file.name);
    setSourceType(
      resolveSourceTypeAfterFilePick({
        current: sourceType,
        filename: file.name,
        userExplicitlySetType: sourceTypeUserSet,
      }),
    );
  }

  function onSourceTypeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setSourceType(e.target.value as SourceType);
    setSourceTypeUserSet(true);
    // If the user moves away from canon_doc, the Activate checkbox is
    // about to unmount; reset to false so we don't carry a hidden
    // is_active=true into a non-canon submission if they bounce back.
    if (e.target.value !== "canon_doc") {
      setActivate(false);
    }
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const fd = new FormData(e.currentTarget);
    // Drop empty optional fields so the API uses its defaults.
    for (const key of ["canonical_doc_id", "version_label", "title"]) {
      if (!String(fd.get(key) ?? "").trim()) fd.delete(key);
    }
    if (!fd.get("is_active_canon_version")) {
      fd.set("is_active_canon_version", "false");
    }
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${apiBase}/sources/upload`, {
        method: "POST",
        body: fd,
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Upload failed (${response.status}): ${detail}`);
      }
      closeDialog();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const isCanon = sourceType === "canon_doc";

  return (
    <>
      <BigButton kind="primary" onClick={() => setOpen(true)}>
        + Upload a document
      </BigButton>

      {open ? (
        <div
          style={OVERLAY}
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) closeDialog();
          }}
          role="presentation"
        >
          <div
            style={PANEL}
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-source-title"
          >
            <h2
              id="upload-source-title"
              className="serif"
              style={{
                fontSize: 26,
                fontWeight: 400,
                margin: "0 0 6px",
                color: "var(--ink)",
                letterSpacing: 0,
                textTransform: "none",
                lineHeight: 1.2,
              }}
            >
              Upload a document
            </h2>
            <p
              style={{
                fontSize: 15,
                color: "var(--ink-soft)",
                margin: "0 0 20px",
                lineHeight: 1.5,
              }}
            >
              The system reads it and pulls out tasks. Processing runs in the background;
              the source will appear in the list with a status that updates as it completes.
            </p>

            <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <FormField label="File">
                <div className="file-input-row">
                  <label className="file-input-trigger">
                    Choose file
                    <input
                      name="file"
                      type="file"
                      required
                      accept={ACCEPT_EXTENSIONS}
                      onChange={onFileChange}
                      className="file-input-hidden"
                    />
                  </label>
                  <span className="file-input-name">
                    {chosenName || "No file chosen"}
                  </span>
                </div>
              </FormField>

              <FormField label="Title" optional>
                <input
                  name="title"
                  type="text"
                  placeholder="Defaults to filename"
                />
              </FormField>

              <FormField label="Source type">
                <select
                  name="source_type"
                  value={sourceType}
                  onChange={onSourceTypeChange}
                  required
                >
                  {SOURCE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {SOURCE_TYPE_LABEL[t]}
                    </option>
                  ))}
                </select>
              </FormField>

              {isCanon ? (
                <>
                  <FormField label="Canonical doc id">
                    <input
                      name="canonical_doc_id"
                      type="text"
                      placeholder="e.g. canon-vendor-onboarding"
                    />
                  </FormField>
                  <FormField label="Version label">
                    <input
                      name="version_label"
                      type="text"
                      placeholder="e.g. v3"
                    />
                  </FormField>
                  {/* Native checkbox kept as-is for FormData + tests +
                      a11y. Brass accent + 22×22 size matches BigCheckbox;
                      we inline rather than wrap because this checkbox
                      needs both `name`, `value`, and `data-testid` and
                      the Activate label sits on a single line. */}
                  <label
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 12,
                      cursor: "pointer",
                      userSelect: "none",
                    }}
                  >
                    <input
                      name="is_active_canon_version"
                      type="checkbox"
                      value="true"
                      checked={activate}
                      onChange={(e) => setActivate(e.target.checked)}
                      data-testid="activate-canon-checkbox"
                      style={{
                        accentColor: "var(--brass)",
                        width: 22,
                        height: 22,
                        cursor: "pointer",
                      }}
                    />
                    <span style={{ fontSize: 15, color: "var(--ink)" }}>
                      Activate as the active canon version on upload
                    </span>
                  </label>
                </>
              ) : null}

              {error ? (
                <div role="alert" style={{ fontSize: 14, color: "var(--danger)" }}>
                  {error}
                </div>
              ) : null}

              <div style={{ display: "flex", gap: 12, marginTop: 6, flexWrap: "wrap" }}>
                <BigButton kind="primary" type="submit" disabled={busy}>
                  {busy ? "Uploading…" : "Upload"}
                </BigButton>
                <BigButton
                  kind="secondary"
                  onClick={closeDialog}
                  disabled={busy}
                >
                  Cancel
                </BigButton>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}

function FormField({
  label,
  optional,
  children,
}: {
  label: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>
        {label}
        {optional ? (
          <span style={{ marginLeft: 6, fontSize: 13, fontWeight: 400, color: "var(--ink-faint)" }}>
            (optional)
          </span>
        ) : null}
      </span>
      {children}
    </label>
  );
}
