import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useEscapeKey } from "../hooks/useEscapeKey";

/** Имя пользователя с выпадающим меню («Сменить пароль», «Выйти»). Раньше имя, ссылка и кнопка
 * стояли в шапке отдельными элементами, и на телефоне занимали ещё две строки. */
export default function UserMenu({ name, onLogout }: { name: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
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
          <Link to="/change-password" role="menuitem" onClick={() => setOpen(false)}>
            Сменить пароль
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            Выйти
          </button>
        </div>
      )}
    </div>
  );
}
