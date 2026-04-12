"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <section className="panel">
      <h2>Unable to load page</h2>
      <p className="small">{error.message}</p>
      <button className="link-btn" onClick={reset} type="button">
        Retry
      </button>
    </section>
  );
}
