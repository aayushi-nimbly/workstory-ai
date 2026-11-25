"use client";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="error-box">
      <h2>Something went wrong</h2>
      <p style={{ margin: 0, color: "var(--text-muted)" }}>
        {process.env.NODE_ENV === "development" ? message : "The page could not be loaded."}
      </p>
      <p style={{ margin: "10px 0 0", color: "var(--text-muted)" }}>
        Is the API running? Start it with <code>uv run uvicorn app.main:app --reload</code> in{" "}
        <code>backend/</code>.
      </p>
      <button onClick={() => retry()}>Try again</button>
    </div>
  );
}
