import type { TaskProgress } from "../../api/types";

const SEGMENTS: { key: keyof TaskProgress; label: string }[] = [
  { key: "accepted", label: "принято" },
  { key: "submitted", label: "на проверке" },
  { key: "in_progress", label: "в работе" },
  { key: "returned", label: "возвращено" },
  { key: "new", label: "не начато" },
];

/** Прогресс задачи по группам одной полосой: принято → на проверке → в работе → возвращено → не начато. */
export default function ProgressStrip({ p, withLegend = false }: { p: TaskProgress; withLegend?: boolean }) {
  const parts = SEGMENTS.filter((s) => p[s.key] > 0);
  const text = parts.map((s) => `${s.label} ${p[s.key]}`).join(", ");
  return (
    <div className="progress-strip">
      <div className="progress-strip__bar" role="img" aria-label={`Из ${p.total} групп: ${text || "нет групп"}`}>
        {parts.map((s) => (
          <i key={s.key} className={`seg-${s.key}`} style={{ flexGrow: p[s.key] }} />
        ))}
      </div>
      <div className="progress-strip__text">
        <span>
          сдано {p.submitted + p.accepted} из {p.total}
        </span>
        {p.overdue > 0 && <b className="progress-strip__overdue">просрочено {p.overdue}</b>}
      </div>
      {withLegend && (
        <div className="progress-strip__legend">
          {SEGMENTS.map((s) => (
            <span key={s.key}>
              <i className={`seg-${s.key}`} aria-hidden="true" />
              {s.label} {p[s.key]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
