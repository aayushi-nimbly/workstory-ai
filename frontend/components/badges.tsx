import type { Involvement, Level } from "@/lib/api";
import {
  COMPLEXITY_COLOR,
  INVOLVEMENT_LABEL,
  capitalize,
  involvementColor,
} from "@/lib/format";

export function Complexity({ level }: { level: Level }) {
  return (
    <span className="cx">
      <i style={{ background: COMPLEXITY_COLOR[level] }} />
      {capitalize(level)}
    </span>
  );
}

/** Shown only for low confidence: high and medium stay quiet to reduce noise. */
export function LowConfidence({ level }: { level: Level }) {
  if (level !== "low") return null;
  return (
    <span className="badge conf-low" title="Low confidence">
      ⚠ Unverified
    </span>
  );
}

export function InvolvementBadge({ involvement }: { involvement: Involvement }) {
  const color = involvementColor(involvement);
  return (
    <span className="inv-badge" style={{ color, borderColor: `color-mix(in srgb, ${color} 35%, transparent)` }}>
      {INVOLVEMENT_LABEL[involvement]}
    </span>
  );
}

export function InvolvementDot({ involvement }: { involvement: Involvement }) {
  return <span className="inv-dot" style={{ background: involvementColor(involvement) }} />;
}
