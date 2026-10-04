import { useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { filterByQuery } from "../utils/searchMatch";

export interface SearchOption {
  value: string;
  label: string;
}

/** Выбор из длинного списка с вводом с клавиатуры. Пока человек печатает, остаются
 * только подходящие варианты (по началу названия; «GD» найдёт «ГД116»), Enter берёт
 * первый из них, стрелки двигают выбор, Esc закрывает. Пункт «все» (allLabel) всегда
 * стоит первым и выбирается значением "" — вызывающий код сам решает, что оно значит. */
export default function SearchSelect({
  value,
  options,
  onChange,
  allLabel,
  placeholder = "Начните вводить…",
  ariaLabel,
  title,
  disabled,
  className,
}: {
  value: string;
  options: SearchOption[];
  onChange: (value: string) => void;
  allLabel?: string;
  placeholder?: string;
  ariaLabel?: string;
  title?: string;
  disabled?: boolean;
  className?: string;
}) {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const selectedLabel = value === "" ? (allLabel ?? "") : (options.find((o) => o.value === value)?.label ?? "");
  const shown = useMemo(() => {
    const found = filterByQuery(options, query, (o) => o.label);
    return allLabel !== undefined && query.trim() === "" ? [{ value: "", label: allLabel }, ...found] : found;
  }, [options, query, allLabel]);

  function pick(option: SearchOption | undefined) {
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(shown.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      if (open) {
        e.preventDefault();
        pick(shown[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className={`search-select${className ? ` ${className}` : ""}`}>
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label={ariaLabel}
        title={title}
        disabled={disabled}
        placeholder={open ? placeholder : undefined}
        value={open ? query : selectedLabel}
        onFocus={(e) => {
          setOpen(true);
          setActive(0);
          e.currentTarget.select();
        }}
        onClick={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onBlur={() => {
          setOpen(false);
          setQuery("");
        }}
        onKeyDown={onKeyDown}
        autoComplete="off"
      />
      {open && (
        <ul id={listId} role="listbox" className="search-select__list">
          {shown.map((o, i) => (
            <li
              key={o.value === "" ? "__all" : o.value}
              role="option"
              aria-selected={o.value === value}
              className={`search-select__option${i === active ? " active" : ""}${o.value === value ? " selected" : ""}`}
              // mousedown, а не click: иначе blur у поля закроет список раньше выбора.
              onMouseDown={(e) => {
                e.preventDefault();
                pick(o);
              }}
              onClick={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
            >
              {o.label}
            </li>
          ))}
          {shown.length === 0 && <li className="search-select__empty">Ничего не найдено</li>}
        </ul>
      )}
    </div>
  );
}
