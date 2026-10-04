import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { MANAGEMENT_ROLES, TASK_MANAGER_ROLES, VIEWER_ROLES, inRoles, leadsGroups } from "../constants/roles";
import NotificationBell from "./NotificationBell";
import UserMenu from "./UserMenu";

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();

  // На телефоне меню — прокручиваемая строка: активный раздел подводим в видимую часть.
  useEffect(() => {
    (navRef.current?.querySelector("a.active") as HTMLElement | null)?.scrollIntoView?.({ inline: "center", block: "nearest" });
  }, [pathname]);

  return (
    <div className="app-shell">
      <div className="brand-accent-line" />
      <header className="app-header">
        <div className="app-header__logo">
          <img src="/kait20-logo.webp" alt="КАИТ №20" />
        </div>
        <nav className="app-header__nav" ref={navRef} aria-label="Разделы">
          {leadsGroups(user) ? (
            <NavLink to="/cabinet" className={({ isActive }) => (isActive ? "active" : "")}>
              Мои группы
            </NavLink>
          ) : null}
          {leadsGroups(user) ? (
            <NavLink to="/my-tasks" className={({ isActive }) => (isActive ? "active" : "")}>
              Мои задачи
            </NavLink>
          ) : null}
          {inRoles(user?.role, TASK_MANAGER_ROLES) && (
            <NavLink to="/tasks" end className={({ isActive }) => (isActive ? "active" : "")}>
              Задачи
            </NavLink>
          )}
          {inRoles(user?.role, VIEWER_ROLES) && (
            <NavLink to="/dashboards" className={({ isActive }) => (isActive ? "active" : "")}>
              Витрины
            </NavLink>
          )}
          {inRoles(user?.role, VIEWER_ROLES) && (
            <NavLink to="/students" className={({ isActive }) => (isActive ? "active" : "")}>
              Студенты
            </NavLink>
          )}
          {(inRoles(user?.role, VIEWER_ROLES) || leadsGroups(user)) && (
            <NavLink to="/passport" className={({ isActive }) => (isActive ? "active" : "")}>
              Соц. паспорт
            </NavLink>
          )}
          {inRoles(user?.role, MANAGEMENT_ROLES) && (
            <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
              Админка
            </NavLink>
          )}
        </nav>
        <div className="app-header__user">
          {user && (
            <>
              <NotificationBell />
              <UserMenu name={user.full_name} onLogout={logout} />
            </>
          )}
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
