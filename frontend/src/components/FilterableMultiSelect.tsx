import { useMemo, useState } from "react";
import type { SearchOption } from "./SearchSelect";
import { filterByQuery } from "../utils/searchMatch";

/** Выбор нескольких вариантов из длинного списка: над списком — строка поиска
 * (например, «GD» оставит группы с ГД). Выбранные, но скрытые поиском варианты не
 * теряются; рядом показано, сколько всего выбрано. */
export default function FilterableMultiSelect({
  options,
  selected,
  onChange,
  size = 8,
  ariaLabel,
  placeholder = "Найти группу, например «ГД»…",
}: {
  options: SearchOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  size?: number;
  ariaLabel?: string;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => filterByQuery(options, query, (o) => o.label), [options, query]);

  function handleChange(chosen: string[]) {
    const visibleValues = new Set(visible.map((o) => o.value));
    // Выбранные варианты, скрытые поиском, остаются как были.
    const hiddenSelected = selected.filter((v) => !visibleValues.has(v));
    onChange([...hiddenSelected, ...chosen]);
  }

  return (
    <div className="filterable-multi">
      <div className="filterable-multi__bar">
        <input
          type="search"
          placeholder={placeholder}
          aria-label={ariaLabel ? `Поиск: ${ariaLabel}` : "Поиск"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="hint">Выбрано: {selected.length}</span>
        {selected.length > 0 && (
          <button type="button" className="link-btn" onClick={() => onChange([])}>
            Снять выбор
          </button>
        )}
      </div>
      <select
        multiple
        size={size}
        style={{ width: "100%" }}
        aria-label={ariaLabel}
        value={selected}
        onChange={(e) => handleChange(Array.from(e.target.selectedOptions, (o) => o.value))}
      >
        {visible.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {query.trim() !== "" && visible.length === 0 && <p className="hint">Ничего не найдено</p>}
    </div>
  );
}
