import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import DepartmentsTab from "./admin/DepartmentsTab";
import GroupsTab from "./admin/GroupsTab";
import StudentsTab from "./admin/StudentsTab";
import MarkCodesTab from "./admin/MarkCodesTab";
import UsersTab from "./admin/UsersTab";
import CalendarTab from "./admin/CalendarTab";
import GroupJournalTab from "./admin/GroupJournalTab";

type Tab = "departments" | "groups" | "students" | "mark-codes" | "users" | "calendar" | "journal";

export default function AdminPage() {
  const { user } = useAuth();
  const isDeptHead = user?.role === "dept_head";
  const [tab, setTab] = useState<Tab>(isDeptHead ? "journal" : "groups");

  // Отделения и справочники (коды отметок, календарь) — зона воспитательного
  // отдела и администратора по всему колледжу, не зав. отделением.
  const isAdmin = user?.role === "admin";
  const isReferenceEditor = user?.role === "admin" || user?.role === "edu_department";
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
