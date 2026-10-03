import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { MANAGEMENT_ROLES, VIEWER_ROLES } from "../constants/roles";
import NotificationBell from "./NotificationBell";

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <div className="brand-accent-line" />
      <header className="app-header">
        <div className="app-header__logo">
          <img src="/kait20-logo.webp" alt="КАИТ №20" />
        </div>
        <nav className="app-header__nav">
          {user && (user.role === "curator" || user.role === "deputy_curator" || user.groups.length > 0) ? (
            <NavLink to="/cabinet" className={({ isActive }) => (isActive ? "active" : "")}>
              Мои группы
            </NavLink>
          ) : null}
          {user && VIEWER_ROLES.includes(user.role) && (
            <NavLink to="/dashboards" className={({ isActive }) => (isActive ? "active" : "")}>
              Витрины
            </NavLink>
          )}
          {user && VIEWER_ROLES.includes(user.role) && (
            <NavLink to="/students" className={({ isActive }) => (isActive ? "active" : "")}>
              Студенты
            </NavLink>
          )}
          {user && (VIEWER_ROLES.includes(user.role) || user.groups.length > 0 || user.role === "curator" || user.role === "deputy_curator") && (
            <NavLink to="/passport" className={({ isActive }) => (isActive ? "active" : "")}>
              Соц. паспорт
            </NavLink>
          )}
          {user && MANAGEMENT_ROLES.includes(user.role) && (
            <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
              Админка
            </NavLink>
          )}
        </nav>
        <div className="app-header__user">
          {user && (
            <>
              <NotificationBell />
              <span>{user.full_name}</span>
              <NavLink to="/change-password">Сменить пароль</NavLink>
              <button onClick={logout}>Выйти</button>
            </>
          )}
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
