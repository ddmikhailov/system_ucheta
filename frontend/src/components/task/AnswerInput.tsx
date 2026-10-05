import type { AnswerField } from "../../utils/taskAnswers";

/** Поле ответа по задаче. Выбор из списка — чипами (одно касание вместо выпадающего списка и мелких
 * флажков), «да/нет» — двумя кнопками; остальное — обычные поля ввода. */
export default function AnswerInput({
  field,
  value,
  onChange,
  label,
  invalid = false,
}: {
  field: AnswerField;
  value: unknown;
  onChange: (v: unknown) => void;
  /** Доступное имя группы кнопок/поля, например «Кружки: Иванова Анна». */
  label: string;
  invalid?: boolean;
}) {
  switch (field.type) {
    case "bool":
      return (
        <div className="choice-seg" role="group" aria-label={label}>
          {[
            [true, "Да"],
            [false, "Нет"],
          ].map(([v, text]) => (
            <button
              key={String(v)}
              type="button"
              aria-pressed={value === v}
              className={value === v ? "on" : ""}
              // Повторное нажатие снимает ответ: «не знаю» лучше пустого, чем случайного «нет».
              onClick={() => onChange(value === v ? null : v)}
            >
              {text as string}
            </button>
          ))}
        </div>
      );
    case "select":
    case "multiselect": {
      const multi = field.type === "multiselect";
      const selected = multi ? (Array.isArray(value) ? (value as string[]) : []) : typeof value === "string" ? [value] : [];
      return (
        <div className="choice-chips" role="group" aria-label={label}>
          {field.options.map((o) => {
            const on = selected.includes(o);
            return (
              <button
                key={o}
                type="button"
                aria-pressed={on}
                className={on ? "on" : ""}
                onClick={() => {
                  if (multi) onChange(on ? selected.filter((x) => x !== o) : [...selected, o]);
                  else onChange(on ? null : o);
                }}
              >
                {o}
              </button>
            );
          })}
        </div>
      );
    }
    case "date":
      return (
        <input
          type="date"
          aria-label={label}
          aria-invalid={invalid || undefined}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "number":
      return (
        <input
          type="text"
          inputMode="decimal"
          aria-label={label}
          aria-invalid={invalid || undefined}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "link":
      return (
        <input
          type="url"
          placeholder="https://…"
          aria-label={label}
          aria-invalid={invalid || undefined}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    default:
      return (
        <input
          type="text"
          aria-label={label}
          aria-invalid={invalid || undefined}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }
}
