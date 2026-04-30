"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const SOURCE_TYPES = [
  "canon_doc",
  "thread_export",
  "transcript",
  "note",
  "board_seed",
] as const;

type SourceType = (typeof SOURCE_TYPES)[number];

const ACCEPT_EXTENSIONS = ".pdf,.txt,.md,.docx,.mp3,.mp4,.m4a,.wav,.ogg,.flac,.webm,.mov";

const EXT_TO_TYPE: Record<string, SourceType> = {
  pdf: "thread_export",
  docx: "canon_doc",
  txt: "note",
  md: "note",
  mp3: "transcript",
  m4a: "transcript",
  wav: "transcript",
  ogg: "transcript",
  flac: "transcript",
  mp4: "transcript",
  webm: "transcript",
  mov: "transcript",
};

function inferType(filename: string): SourceType {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TO_TYPE[ext] ?? "note";
}

export default function UploadSource() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chosenName, setChosenName] = useState<string>("");
  const [sourceType, setSourceType] = useState<SourceType>("note");

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) {
      setChosenName("");
      return;
    }
    setChosenName(file.name);
    setSourceType(inferType(file.name));
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const fd = new FormData(e.currentTarget);
    // Drop empty optional fields so the API uses its defaults.
    for (const key of ["canonical_doc_id", "version_label"]) {
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
      setOpen(false);
      setChosenName("");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="badge"
        style={{ padding: "0.4rem 0.75rem", border: "none", cursor: "pointer" }}
      >
        + Upload Source
      </button>
    );
  }

  const isCanon = sourceType === "canon_doc";

  return (
    <form onSubmit={onSubmit} className="stack-sm" style={{ marginTop: "0.5rem" }}>
      <label className="stack-sm">
        <span>File</span>
        <input
          name="file"
          type="file"
          required
          accept={ACCEPT_EXTENSIONS}
          onChange={onFileChange}
        />
      </label>

      <label className="stack-sm">
        <span>Source type</span>
        <select
          name="source_type"
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as SourceType)}
          required
        >
          {SOURCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      {isCanon ? (
        <>
          <label className="stack-sm">
            <span>Canonical doc id</span>
            <input
              name="canonical_doc_id"
              type="text"
              placeholder="e.g. canon-vendor-onboarding"
            />
          </label>
          <label className="stack-sm">
            <span>Version label</span>
            <input name="version_label" type="text" placeholder="e.g. v3" />
          </label>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input name="is_active_canon_version" type="checkbox" value="true" />
            <span className="small">Activate as the active canon version on upload</span>
          </label>
        </>
      ) : null}

      {chosenName ? (
        <div className="small">Selected: {chosenName}</div>
      ) : null}

      {error ? (
        <div className="small" role="alert" style={{ color: "#991b1b" }}>
          {error}
        </div>
      ) : null}

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="submit" disabled={busy}>
          {busy ? "Uploading…" : "Upload"}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
            setChosenName("");
          }}
          disabled={busy}
        >
          Cancel
        </button>
      </div>
      <p className="small" style={{ color: "#6b7280" }}>
        After upload, processing runs in the background — the source will appear in the list with a
        status badge that updates as it completes.
      </p>
    </form>
  );
}
