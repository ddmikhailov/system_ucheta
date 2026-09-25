import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import DepartmentsTab from "./admin/DepartmentsTab";
import GroupsTab from "./admin/GroupsTab";
import StudentsTab from "./admin/StudentsTab";
import MarkCodesTab from "./admin/MarkCodesTab";
import UsersTab from "./admin/UsersTab";
import CalendarTab from "./admin/CalendarTab";
import GroupJournalTab from "./admin/GroupJournalTab";

type Tab = "departments" | "groups" | "students" | "mark-codes" | "users" | "calendar" | "journal";

const VALID_TABS: Tab[] = ["departments", "groups", "students", "mark-codes", "users", "calendar", "journal"];

export default function AdminPage() {
  const { user } = useAuth();
  const isDeptHead = user?.role === "dept_head";
  const [searchParams, setSearchParams] = useSearchParams();
  // Вкладка теперь живёт в URL (?tab=...) — раньше сбрасывалась при
  // обновлении страницы, и на неё нельзя было дать прямую ссылку (см.
  // TODO.md 4; заодно на это опирается переход по клику на уведомление).
  const tabFromUrl = searchParams.get("tab") as Tab | null;
  const [tab, setTabState] = useState<Tab>(
    tabFromUrl && VALID_TABS.includes(tabFromUrl) ? tabFromUrl : isDeptHead ? "journal" : "groups"
  );

  function setTab(next: Tab) {
    setTabState(next);
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    if (next !== "journal") {
      params.delete("group");
      params.delete("date");
    }
    setSearchParams(params, { replace: true });
  }

  // Тьютор — второй полноценный администратор по всему колледжу (обновление
  // 1.2): везде, где раньше был только admin, теперь и он.
  const isAdmin = user?.role === "admin" || user?.role === "tutor";
  const isReferenceEditor = isAdmin || user?.role === "edu_department";
  // Группы/студенты/пользователи — администратор по колледжу и зав.
  // отделением в своём отделении (бэкенд сам ограничивает область видимости).
  const canManageStructure = isAdmin || isDeptHead;

  const tabs: { key: Tab; label: string }[] = isDeptHead
    ? [
        { key: "journal", label: "Журнал группы" },
        { key: "groups", label: "Группы" },
        { key: "students", label: "Студенты" },
        { key: "users", label: "Пользователи" },
      ]
    : [
        { key: "departments", label: "Отделения" },
        { key: "groups", label: "Группы" },
        { key: "students", label: "Студенты" },
        { key: "mark-codes", label: "Коды отметок" },
        { key: "users", label: "Пользователи" },
        { key: "calendar", label: "Календарь" },
        { key: "journal", label: "Журнал группы" },
      ];

  return (
    <div>
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "departments" && <DepartmentsTab canEdit={isAdmin} />}
      {tab === "groups" && <GroupsTab canEdit={canManageStructure} canCreate={isAdmin} />}
      {tab === "students" && <StudentsTab canEdit={canManageStructure} canCreate={isAdmin} />}
      {tab === "mark-codes" && <MarkCodesTab canEdit={isReferenceEditor} />}
      {tab === "users" && <UsersTab canEdit={canManageStructure} canCreate={isAdmin} />}
      {tab === "calendar" && <CalendarTab canEdit={isReferenceEditor} />}
      {tab === "journal" && <GroupJournalTab />}
    </div>
  );
}
