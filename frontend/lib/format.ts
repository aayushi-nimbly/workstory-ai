import type { Involvement, Level } from "./api";

export const INVOLVEMENT_ORDER: Involvement[] = [
  "implemented",
  "collaborated",
  "modified",
  "used",
  "discussed",
  "mentioned",
];

export const INVOLVEMENT_LABEL: Record<Involvement, string> = {
  implemented: "Implemented",
  collaborated: "Collaborated",
  modified: "Modified",
  used: "Used",
  discussed: "Discussed only",
  mentioned: "Mentioned only",
};

export const involvementColor = (inv: Involvement) => `var(--inv-${inv})`;

export const COMPLEXITY_COLOR: Record<Level, string> = {
  high: "var(--high)",
  medium: "var(--medium)",
  low: "var(--low)",
};

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function month(date: string): string {
  return new Date(`${date}T00:00:00`).toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
  });
}

/** "Feb 2025 – Apr 2025", "Oct 2025", or "No PRs". */
export function dateRange(start: string | null, end: string | null): string {
  if (!start) return "No PRs";
  const from = month(start);
  const to = end ? month(end) : from;
  return from === to ? from : `${from} – ${to}`;
}
