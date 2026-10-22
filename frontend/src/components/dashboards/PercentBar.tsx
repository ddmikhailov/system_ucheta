export default function PercentBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    // День не сдан — раньше это молча считалось за 100% (см. TODO.md 3).
    return <span className="hint">—</span>;
  }
  const color = value >= 95 ? "var(--ok)" : value >= 85 ? "var(--warn)" : "var(--danger)";
  const textColor = value >= 95 ? "var(--ok)" : value >= 85 ? "var(--warn-ink)" : "var(--danger)";
  return (
    <div className="percent-bar">
      <div className="percent-bar__track">
        <div className="percent-bar__fill" style={{ width: `${Math.min(value, 100)}%`, background: color }} />
      </div>
      <span className="percent-bar__value" style={{ color: textColor }}>
        {value.toFixed(1)}%
      </span>
    </div>
  );
}
