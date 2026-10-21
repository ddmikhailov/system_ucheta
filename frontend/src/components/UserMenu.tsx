import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { APP_VERSION } from "../constants/release";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { getThemePref, setThemePref } from "../utils/theme";
import type { ThemePref } from "../utils/theme";
import ProblemReportModal from "./ProblemReportModal";

const THEMES: [ThemePref, string][] = [
  ["system", "Как в системе"],
  ["light", "Светлая"],
  ["dark", "Тёмная"],
];

/** Имя пользователя с выпадающим меню («Сменить пароль», «Сообщить о проблеме», «Выйти», номер версии).
 * Раньше имя, ссылка и кнопка стояли в шапке отдельными элементами, и на телефоне занимали ещё две строки. */
export default function UserMenu({ name, onLogout }: { name: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [theme, setTheme] = useState<ThemePref>(getThemePref);
  const ref = useRef<HTMLDivElement>(null);

  useEscapeKey(() => setOpen(false));

  useEffect(() => {
    if (!open) return;
    function onOutsideClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [open]);

  return (
    <div className="user-menu" ref={ref}>
      <button
        type="button"
        className="user-menu__toggle"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="user-menu__name">{name}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="user-menu__panel" role="menu">
          <div className="user-menu__group" role="group" aria-label="Тема оформления">
            <span className="user-menu__caption" aria-hidden="true">
              Тема
            </span>
            {THEMES.map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="menuitemradio"
                aria-checked={theme === value}
                className={theme === value ? "is-checked" : ""}
                onClick={() => {
                  setThemePref(value);
                  setTheme(value);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <Link to="/change-password" role="menuitem" onClick={() => setOpen(false)}>
            Сменить пароль
          </Link>
          <button
            type="button"
            role="menuitem"
            // Класс нужен, чтобы общее оформление кнопок без класса (controls.css) не центрировало пункт меню.
            className="user-menu__item"
            onClick={() => {
              setOpen(false);
              setReporting(true);
            }}
          >
            Сообщить о проблеме
          </button>
          <button
            type="button"
            role="menuitem"
            className="user-menu__item"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            Выйти
          </button>
          <span className="user-menu__version">Версия {APP_VERSION}</span>
        </div>
      )}
      {reporting && <ProblemReportModal onClose={() => setReporting(false)} />}
    </div>
  );
}
