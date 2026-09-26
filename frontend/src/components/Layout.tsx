import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { MANAGEMENT_ROLES } from "../constants/roles";
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
          {user?.role === "curator" || user?.role === "deputy_curator" ? (
            <NavLink to="/cabinet" className={({ isActive }) => (isActive ? "active" : "")}>
              Мои группы
            </NavLink>
          ) : null}
          {user && MANAGEMENT_ROLES.includes(user.role) && (
            <NavLink to="/dashboards" className={({ isActive }) => (isActive ? "active" : "")}>
              Витрины
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
