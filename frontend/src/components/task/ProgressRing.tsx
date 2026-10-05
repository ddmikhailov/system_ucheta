const R = 15.5;
const LENGTH = 2 * Math.PI * R;

/** Кольцо «заполнено N из M». Заполняется плавно — видно, что каждая отметка засчитана. */
export default function ProgressRing({ done, total, label }: { done: number; total: number; label: string }) {
  const share = total > 0 ? Math.min(done / total, 1) : 0;
  return (
    <div className={`progress-ring${total > 0 && done >= total ? " is-complete" : ""}`} role="img" aria-label={label}>
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle cx="18" cy="18" r={R} className="progress-ring__track" />
        {share > 0 && (
          <circle cx="18" cy="18" r={R} className="progress-ring__value" strokeDasharray={`${share * LENGTH} ${LENGTH}`} />
        )}
      </svg>
      <b>
        {done}/{total}
      </b>
    </div>
  );
}
