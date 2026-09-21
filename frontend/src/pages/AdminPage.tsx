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
  const [tab, setTab] = useState<Tab>("groups");
  const { user } = useAuth();

  // Отделения/группы/студенты/пользователи — структурные операции, только администратор.
  const isAdmin = user?.role === "admin";
  // Справочники (коды отметок, календарь) — зона воспитательного отдела и администратора.
  const isReferenceEditor = user?.role === "admin" || user?.role === "edu_department";

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
      {tab === "users" && <UsersTab canEdit={isAdmin} />}
      {tab === "calendar" && <CalendarTab canEdit={isReferenceEditor} />}
    </div>
  );
}
