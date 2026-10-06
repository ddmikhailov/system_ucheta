import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { MeResponse } from "../api/types";
import { MANAGEMENT_ROLES, TEACHER_ROLES, inRoles } from "../constants/roles";
import { filterByQuery } from "../utils/searchMatch";

export interface PaletteSection {
  to: string;
  label: string;
}

interface Command {
  id: string;
  label: string;
  hint: string;
  to: string;
}

interface StudentRow {
  id: number;
  full_name: string;
  group_code: string;
  status: string;
}

const ADMIN_PAGES: PaletteSection[] = [
  { to: "/admin?tab=users", label: "Пользователи" },
  { to: "/admin?tab=journal", label: "Журнал группы" },
  { to: "/admin?tab=groups", label: "Группы" },
  { to: "/admin?tab=students", label: "Студенты (список)" },
  { to: "/admin?tab=calendar", label: "Учебный календарь" },
];

/** Быстрый переход (Ctrl+K / ⌘K, как в Linear и GitHub): разделы, свои группы и поиск
 * студента по ФИО или группе — с клавиатуры, без меню. Поиск студентов — только тем ролям,
 * которым его даёт сервер (куратор ищет в «Моих группах»). */
export default function CommandPalette({
  user,
  sections,
  onClose,
}: {
  user: MeResponse;
  sections: PaletteSection[];
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [students, setStudents] = useState<StudentRow[]>([]);
  const canSearchStudents = !inRoles(user.role, TEACHER_ROLES);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Студенты — с сервера, с паузой после ввода, чтобы не слать запрос на каждую букву.
  const trimmed = query.trim();
  useEffect(() => {
    if (!canSearchStudents || trimmed.length < 2) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api
        .get<StudentRow[]>(`/students?q=${encodeURIComponent(trimmed)}&limit=8`)
        .then((rows) => {
          if (!cancelled) setStudents(rows);
        })
        .catch(() => {
          if (!cancelled) setStudents([]);
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmed, canSearchStudents]);

  const commands = useMemo<Command[]>(() => {
    const base: Command[] = [
      ...sections.map((s) => ({ id: `s:${s.to}`, label: s.label, hint: "Раздел", to: s.to })),
      ...user.groups.map((g) => ({ id: `g:${g.id}`, label: `${g.code} · ${g.course} курс`, hint: "Группа", to: `/cabinet/groups/${g.id}` })),
      ...(inRoles(user.role, MANAGEMENT_ROLES)
        ? ADMIN_PAGES.map((s) => ({ id: `a:${s.to}`, label: s.label, hint: "Админка", to: s.to }))
        : []),
    ];
    const filtered = trimmed ? filterByQuery(base, trimmed, (c) => `${c.label} ${c.hint}`) : base;
    const found =
      canSearchStudents && trimmed.length >= 2
        ? students.map((s) => ({ id: `st:${s.id}`, label: s.full_name, hint: `Студент · ${s.group_code}`, to: `/students/${s.id}` }))
        : [];
    return [...filtered, ...found];
  }, [sections, user, trimmed, students, canSearchStudents]);

  const activeIndex = Math.min(active, Math.max(commands.length - 1, 0));

  function go(c: Command) {
    onClose();
    navigate(c.to);
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((activeIndex + 1) % Math.max(commands.length, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((activeIndex - 1 + commands.length) % Math.max(commands.length, 1));
    } else if (e.key === "Enter" && commands[activeIndex]) {
      e.preventDefault();
      go(commands[activeIndex]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Быстрый переход" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette__input"
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-list"
          aria-activedescendant={commands[activeIndex] ? `palette-${commands[activeIndex].id}` : undefined}
          aria-label="Куда перейти"
          placeholder={canSearchStudents ? "Раздел, группа или студент…" : "Раздел или группа…"}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
        />
        <ul id="palette-list" className="palette__list" role="listbox" aria-label="Варианты">
          {commands.length === 0 ? (
            <li className="palette__empty">Ничего не найдено</li>
          ) : (
            commands.map((c, i) => (
              <li
                key={c.id}
                id={`palette-${c.id}`}
                role="option"
                aria-selected={i === activeIndex}
                className={`palette__item${i === activeIndex ? " is-active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(c)}
              >
                <span className="palette__label">{c.label}</span>
                <span className="palette__hint">{c.hint}</span>
              </li>
            ))
          )}
        </ul>
        <p className="palette__footer" aria-hidden="true">
          <kbd>↑</kbd>
          <kbd>↓</kbd> выбрать · <kbd>Enter</kbd> открыть · <kbd>Esc</kbd> закрыть
        </p>
      </div>
    </div>
  );
}
