export function Placeholder({ title, text, stage }: { title: string; text: string; stage: number }) {
  return (
    <div className="placeholder">
      <div className="big">✦</div>
      <h1>{title}</h1>
      <p className="subtitle">{text}</p>
      <p style={{ color: "var(--text-faint)", marginTop: 14 }}>Coming in Stage {stage}</p>
    </div>
  );
}
