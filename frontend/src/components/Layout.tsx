import { Suspense, useEffect, useRef, useState } from "react";
import BrandMark from "./BrandMark";
import CommandPalette from "./CommandPalette";
import ErrorBoundary from "./ErrorBoundary";
import { PLATFORM_NAME } from "../constants/brand";
import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { MODULE } from "../constants/modules";
import type { ModuleName } from "../constants/modules";
import { isModuleOn } from "../utils/modules";
import { MANAGEMENT_ROLES, MEAL_VIEW_ROLES, TASK_MANAGER_ROLES, VIEWER_ROLES, inRoles, leadsGroups } from "../constants/roles";
import { useEscapeKey } from "../hooks/useEscapeKey";
import type { MeResponse } from "../api/types";
import NavIcon from "./NavIcon";
import type { NavIconName } from "./NavIcon";
import NotificationBell from "./NotificationBell";
import UserMenu from "./UserMenu";
import WhatsNewBanner from "./WhatsNewBanner";
import { pageTitle } from "../utils/pageTitle";
import { dialogs, toast } from "../utils/feedback";
import { clearJournalDrafts, hasJournalDrafts } from "../utils/journalDraft";

type CounterKey = "my_day" | "my_tasks" | "review" | "journal_changes";
type Counters = Partial<Record<CounterKey, number>>;

interface NavItem {
  to: string;
  label: string;
  /** Короткая подпись для нижней панели на телефоне. */
  short?: string;
  icon: NavIconName;
  counter?: CounterKey;
  end?: boolean;
}

/** Разделы по роли и по включённым модулям (релиз 3.5.0) — в том же порядке, что и раньше в верхнем меню. */
function navItems(user: MeResponse | null): NavItem[] {
  const items: NavItem[] = [];
  const role = user?.role;
  const on = (name: ModuleName) => isModuleOn(user, name);
  if (leadsGroups(user)) {
    items.push({ to: "/my-day", label: "Мой день", icon: "day", counter: "my_day" });
    items.push({ to: "/cabinet", label: "Мои группы", short: "Группы", icon: "groups" });
    if (on(MODULE.TASKS)) items.push({ to: "/my-tasks", label: "Мои задачи", short: "Задачи", icon: "inbox", counter: "my_tasks" });
  }
  if (inRoles(role, TASK_MANAGER_ROLES) && on(MODULE.TASKS)) items.push({ to: "/tasks", label: "Задачи", icon: "tasks", counter: "review", end: true });
  if (inRoles(role, VIEWER_ROLES)) {
    items.push({ to: "/dashboards", label: "Витрины", icon: "charts" });
    items.push({ to: "/students", label: "Студенты", icon: "students" });
  }
  // Куратору соц. паспорт, индивидуальная работа, план и отчёт — во вкладках его группы («Мои группы»);
  // отдельными разделами меню они остаются у тех, кто смотрит много групп.
  if (inRoles(role, VIEWER_ROLES)) {
    if (on(MODULE.PASSPORT)) items.push({ to: "/passport", label: "Соц. паспорт", short: "Паспорт", icon: "passport" });
    if (on(MODULE.INDIVIDUAL_WORK)) items.push({ to: "/individual-work", label: "Индивидуальная работа", short: "Работа", icon: "individual" });
    if (on(MODULE.PLAN)) items.push({ to: "/plan", label: "План группы", short: "План", icon: "plan" });
    if (on(MODULE.REPORTS)) items.push({ to: "/report", label: "Отчёт куратора", short: "Отчёт", icon: "report" });
    if (on(MODULE.MY_ID)) items.push({ to: "/my-id", label: "Мой ID", short: "ID", icon: "id" });
  }
  if (inRoles(role, MEAL_VIEW_ROLES) && on(MODULE.MEALS)) items.push({ to: "/meals", label: "Питание", icon: "meals" });
  if (inRoles(role, MANAGEMENT_ROLES)) items.push({ to: "/admin", label: "Админка", icon: "admin", counter: "journal_changes" });
  return items;
}

function Badge({ value, label }: { value: number | undefined; label: string }) {
  if (!value) return null;
  return (
    <span className="nav-badge">
      <span aria-hidden="true">{value > 99 ? "99+" : value}</span>
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

const COUNTER_LABELS: Record<CounterKey, string> = {
  my_day: "дел на сегодня",
  my_tasks: "задач требуют внимания",
  review: "ответов ждут проверки",
  journal_changes: "исправлений журнала ждут решения",
};

/** Общая рамка страниц: родительский маршрут рисует раздел через <Outlet/>; children — для тестов и вложения вручную. */
export default function Layout({ children }: { children?: ReactNode }) {
  const { user, logout, logoutAll, refresh } = useAuth();
  // Настройка про журнал дня нужна тем, кто ведёт группу.
  const showCarryOver = (user?.groups.length ?? 0) > 0;
  async function changeCarryOver(value: boolean) {
    await api.patch("/auth/preferences", { carry_over_marks: value });
    await refresh();
  }
  const { pathname } = useLocation();
  const [counters, setCounters] = useState<Counters>({});
  const [moreOpen, setMoreOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const items = navItems(user);
  const title = pageTitle(pathname);
  useEffect(() => {
    document.title = title === PLATFORM_NAME ? `${PLATFORM_NAME} — КАИТ №20` : `${title} — ${PLATFORM_NAME}`;
  }, [title]);

  // Счётчики на пунктах меню обновляем при каждом переходе: сдали день, отправили задачу — число уменьшилось.
  useEffect(() => {
    if (!user) return;
    api
      .get<Counters>("/my-day/counters")
      .then((c) => setCounters(c && typeof c === "object" && !Array.isArray(c) ? c : {}))
      .catch(() => setCounters({}));
  }, [pathname, user]);

  const [closedOn, setClosedOn] = useState(pathname);
  if (closedOn !== pathname) {
    // Переход — закрываем лист «Ещё».
    setClosedOn(pathname);
    if (moreOpen) setMoreOpen(false);
  }
  // Несданные отметки журнала после выхода пропадут: переспрашиваем, а на выходе стираем черновики вкладки.
  async function confirmDrafts(): Promise<boolean> {
    if (!hasJournalDrafts()) return true;
    return dialogs.confirm("Отметки журнала не сданы и пропадут после выхода. Всё равно выйти?", { confirmLabel: "Выйти", danger: true });
  }

  async function handleLogout() {
    if (!(await confirmDrafts())) return;
    clearJournalDrafts();
    logout();
  }

  async function handleLogoutAll() {
    const ok = await dialogs.confirm(
      "Выйти на всех устройствах? Вход завершится везде: на этом компьютере, телефоне и в других браузерах. Пароль не меняется.",
      { confirmLabel: "Выйти везде" }
    );
    if (!ok || !(await confirmDrafts())) return;
    try {
      await logoutAll();
      clearJournalDrafts();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Не удалось выйти на всех устройствах — проверьте связь", "error");
    }
  }

  // Быстрый переход: Ctrl+K / ⌘K откуда угодно, «/» — если курсор не в поле ввода.
  const [paletteOpen, setPaletteOpen] = useState(false);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = !!target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
      if ((e.key === "k" || e.key === "K" || e.key === "л" || e.key === "Л") && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      } else if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const paletteButtonRef = useRef<HTMLButtonElement>(null);
  function closePalette() {
    setPaletteOpen(false);
    paletteButtonRef.current?.focus();
  }

  useEscapeKey(() => {
    if (!moreOpen) return;
    setMoreOpen(false);
    moreButtonRef.current?.focus();
  });

  // Открыли лист «Ещё» — фокус на первый раздел, чтобы с клавиатуры не искать его по всей странице.
  useEffect(() => {
    if (moreOpen) sheetRef.current?.querySelector<HTMLElement>("a")?.focus();
  }, [moreOpen]);

  // На телефоне внизу — четыре места: три первых раздела и «Ещё», если разделов больше.
  const tabItems = items.length > 4 ? items.slice(0, 3) : items;
  const rest = items.length > 4 ? items.slice(3) : [];
  const restActive = rest.some((i) => pathname.startsWith(i.to));

  const link = (item: NavItem, variant: "side" | "tab" | "sheet") => (
    <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `nav-link nav-link--${variant}${isActive ? " active" : ""}`}>
      <NavIcon name={item.icon} />
      <span className="nav-link__label">{variant === "tab" ? (item.short ?? item.label) : item.label}</span>
      {item.counter && <Badge value={counters[item.counter]} label={`${counters[item.counter]} ${COUNTER_LABELS[item.counter]}`} />}
    </NavLink>
  );

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar__logo">
          <BrandMark />
        </div>
        <nav className="app-nav" aria-label="Разделы">
          {items.map((i) => link(i, "side"))}
        </nav>
      </aside>

      <div className="app-body">
        <div className="brand-accent-line" />
        <header className="app-topbar">
          <div className="app-topbar__logo">
            <BrandMark compact />
          </div>
          {user && (
            <button
              ref={paletteButtonRef}
              type="button"
              className="palette-trigger"
              aria-haspopup="dialog"
              aria-keyshortcuts="Control+K"
              aria-label="Быстрый переход"
              title="Быстрый переход (Ctrl+K)"
              onClick={() => setPaletteOpen(true)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
                <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span className="palette-trigger__text">Быстрый переход</span>
              <kbd className="palette-trigger__kbd">Ctrl K</kbd>
            </button>
          )}
          <div className="app-header__user">
            {user && (
              <>
                <NotificationBell />
                <UserMenu
                  name={user.full_name}
                  onLogout={handleLogout}
                  onLogoutAll={handleLogoutAll}
                  carryOver={showCarryOver ? user.carry_over_marks ?? true : undefined}
                  onCarryOverChange={changeCarryOver}
                />
              </>
            )}
          </div>
        </header>
        <main className="app-main">
          <h1 className="visually-hidden">{title}</h1>
          <WhatsNewBanner />
          {/* Раздел, который грузится по требованию: меню остаётся на месте, пока он подгружается. Сбой раздела
              не роняет меню, а переход в другой раздел (key) снимает сообщение об ошибке. */}
          <ErrorBoundary key={pathname}>
            <Suspense fallback={<p className="hint">Загрузка…</p>}>{children ?? <Outlet />}</Suspense>
          </ErrorBoundary>
        </main>
      </div>

      {items.length > 0 && (
        <nav className="app-tabbar" aria-label="Быстрые разделы">
          {tabItems.map((i) => link(i, "tab"))}
          {rest.length > 0 && (
            <button
              ref={moreButtonRef}
              type="button"
              className={`nav-link nav-link--tab${restActive ? " active" : ""}`}
              aria-expanded={moreOpen}
              aria-haspopup="dialog"
              onClick={() => setMoreOpen((v) => !v)}
            >
              <NavIcon name="more" />
              <span className="nav-link__label">Ещё</span>
            </button>
          )}
        </nav>
      )}
      {paletteOpen && user && (
        <CommandPalette user={user} sections={items.map((i) => ({ to: i.to, label: i.label }))} onClose={closePalette} />
      )}
      {moreOpen && (
        <div className="more-sheet-backdrop" onClick={() => setMoreOpen(false)}>
          <div ref={sheetRef} className="more-sheet" role="dialog" aria-modal="true" aria-label="Все разделы" onClick={(e) => e.stopPropagation()}>
            {rest.map((i) => link(i, "sheet"))}
          </div>
        </div>
      )}
    </div>
  );
}
