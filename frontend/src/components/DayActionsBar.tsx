// Максимум пар в день, который предлагает интерфейс (бэкенд принимает до 10).
const PERIOD_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8];

/** Панель над списком студентов: «Все присутствуют», «Сдать день» и выбор
 * пары, к которой группа пришла в этот день (идёт в свод «всего / к 1 паре»). */
export default function DayActionsBar({
  absentCount,
  busy,
  firstPeriod,
  onFirstPeriodChange,
  onAllPresent,
  onSubmit,
  submitLabel = "Сдать день",
  planMode = false,
}: {
  absentCount: number;
  busy: boolean;
  firstPeriod: string;
  onFirstPeriodChange: (value: string) => void;
  onAllPresent: () => void;
  onSubmit: () => void;
  submitLabel?: string;
  /** Будущий день: отметки только планируются — без «Все присутствуют» и выбора пары. */
  planMode?: boolean;
}) {
  return (
    <div className="day-actions">
      <span className="absent-counter">Отсутствуют: {absentCount}</span>
      {!planMode && (
        <button onClick={onAllPresent} disabled={busy}>
          Все присутствуют
        </button>
      )}
      <button onClick={onSubmit} disabled={busy}>
        {submitLabel}
      </button>
      {!planMode && (
      <label className="day-actions__period">
        К какой паре пришли
        <select value={firstPeriod} onChange={(e) => onFirstPeriodChange(e.target.value)}>
          <option value="">не указано</option>
          {PERIOD_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n} пара
            </option>
          ))}
        </select>
      </label>
      )}
    </div>
  );
}
