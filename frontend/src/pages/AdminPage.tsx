import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import DepartmentsTab from "./admin/DepartmentsTab";
import GroupsTab from "./admin/GroupsTab";
import StudentsTab from "./admin/StudentsTab";
import MarkCodesTab from "./admin/MarkCodesTab";
import UsersTab from "./admin/UsersTab";
import CalendarTab from "./admin/CalendarTab";

type Tab = "departments" | "groups" | "students" | "mark-codes" | "users" | "calendar";

export default function AdminPage() {
  const { user } = useAuth();
  const isDeptHead = user?.role === "dept_head";
  const [tab, setTab] = useState<Tab>(isDeptHead ? "users" : "groups");

  // Отделения/группы/студенты — структурные операции, только администратор
  // (полное редактирование этих списков зав. отделением — следующий модуль).
  const isAdmin = user?.role === "admin";
  // Справочники (коды отметок, календарь) — зона воспитательного отдела и администратора.
  const isReferenceEditor = user?.role === "admin" || user?.role === "edu_department";
  // Логины/пароли — администратор по всему колледжу, зав. отделением в своём.
  const canManageUsers = isAdmin || isDeptHead;

  // Зав. отделением заходит в админку только за управлением логинами/паролями
  // своих кураторов — остальные вкладки пока не про него (см. модуль
  // «полное управление списками»).
  if (isDeptHead) {
    return (
      <div>
        <UsersTab canEdit={canManageUsers} canCreate={false} />
      </div>
    );
  }

  return (
    <div>
      <div className="tabs">
        <button className={tab === "departments" ? "active" : ""} onClick={() => setTab("departments")}>
          Отделения
        </button>
        <button className={tab === "groups" ? "active" : ""} onClick={() => setTab("groups")}>
          Группы
        </button>
        <button className={tab === "students" ? "active" : ""} onClick={() => setTab("students")}>
          Студенты
        </button>
        <button className={tab === "mark-codes" ? "active" : ""} onClick={() => setTab("mark-codes")}>
          Коды отметок
        </button>
        <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
          Пользователи
        </button>
        <button className={tab === "calendar" ? "active" : ""} onClick={() => setTab("calendar")}>
          Календарь
        </button>
      </div>

      {tab === "departments" && <DepartmentsTab canEdit={isAdmin} />}
      {tab === "groups" && <GroupsTab canEdit={isAdmin} />}
      {tab === "students" && <StudentsTab canEdit={isAdmin} />}
      {tab === "mark-codes" && <MarkCodesTab canEdit={isReferenceEditor} />}
      {tab === "users" && <UsersTab canEdit={canManageUsers} canCreate={isAdmin} />}
      {tab === "calendar" && <CalendarTab canEdit={isReferenceEditor} />}
    </div>
  );
}
