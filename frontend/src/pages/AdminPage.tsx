import { useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import DepartmentsTab from "./admin/DepartmentsTab";
import GroupsTab from "./admin/GroupsTab";
import StudentsTab from "./admin/StudentsTab";
import MarkCodesTab from "./admin/MarkCodesTab";
import UsersTab from "./admin/UsersTab";
import CalendarTab from "./admin/CalendarTab";
import GroupJournalTab from "./admin/GroupJournalTab";
import ImportTab from "./admin/ImportTab";
import DebugTab from "./admin/DebugTab";
import { saveTabSearch, savedTabSearch } from "../utils/navMemory";
import { DEPARTMENT_SCOPED_ROLES, REFERENCE_EDITOR_ROLES, ROLE, inRoles } from "../constants/roles";

type Tab = "departments" | "groups" | "students" | "mark-codes" | "users" | "calendar" | "journal" | "import" | "debug";

const VALID_TABS: Tab[] = ["departments", "groups", "students", "mark-codes", "users", "calendar", "journal", "import", "debug"];

export default function AdminPage() {
  const { user } = useAuth();
  // Зав. отделением и тьютор работают в границах своего отделения.
  // Воспитательный отдел тоже привязан к отделению, но вкладки у него свои (справочники общие) — их задаёт isReferenceEditor.
  const isDeptHead = inRoles(user?.role, DEPARTMENT_SCOPED_ROLES) && !inRoles(user?.role, REFERENCE_EDITOR_ROLES);
  const [searchParams, setSearchParams] = useSearchParams();
  // Вкладка теперь живёт в URL (?tab=...) — раньше сбрасывалась при
  // обновлении страницы, и на неё нельзя было дать прямую ссылку (см.
  // TODO.md 4; заодно на это опирается переход по клику на уведомление).
  const tabFromUrl = searchParams.get("tab") as Tab | null;
  const tab: Tab = tabFromUrl && VALID_TABS.includes(tabFromUrl) ? tabFromUrl : isDeptHead ? "journal" : "groups";

  // У каждой вкладки свои параметры в адресе (группа, поиск, фильтры, страница). Уходя с вкладки,
  // запоминаем их, а вернувшись — восстанавливаем: «Студенты» снова открываются на той же группе.
  function setTab(next: Tab) {
    if (next === tab) return;
    saveTabSearch("admin", tab, searchParams.toString());
    const params = new URLSearchParams(savedTabSearch("admin", next) ?? "");
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  }

  // Администратор — по всему колледжу; зав. отделением и тьютор — те же возможности
  // (создание, правка), но только в своём отделении, остальное ограничивает бэкенд.
  const isAdmin = user?.role === ROLE.ADMIN;
  const canCreate = isAdmin || isDeptHead;
  const isReferenceEditor = inRoles(user?.role, REFERENCE_EDITOR_ROLES);
  // Группы/студенты/пользователи — администратор по колледжу и зав.
  // отделением в своём отделении (бэкенд сам ограничивает область видимости).
  const canManageStructure = isAdmin || isDeptHead;

  const tabs: { key: Tab; label: string }[] = isDeptHead
    ? [
        { key: "journal", label: "Журнал группы" },
        { key: "groups", label: "Группы" },
        { key: "students", label: "Студенты" },
        { key: "users", label: "Пользователи" },
        { key: "calendar", label: "Календарь" },
      ]
    : [
        { key: "departments", label: "Отделения" },
        { key: "groups", label: "Группы" },
        { key: "students", label: "Студенты" },
        { key: "mark-codes", label: "Коды отметок" },
        { key: "users", label: "Пользователи" },
        { key: "calendar", label: "Календарь" },
        { key: "journal", label: "Журнал группы" },
        // Массовая загрузка контингента — только администратор (бэкенд проверяет роль).
        ...(isAdmin ? [{ key: "import" as Tab, label: "Импорт" }] : []),
        // Полный журнал действий для разбора сбоев — только администратор (бэкенд проверяет роль).
        ...(isAdmin ? [{ key: "debug" as Tab, label: "Отладка" }] : []),
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
      {tab === "groups" && <GroupsTab canEdit={canManageStructure} canCreate={canCreate} />}
      {tab === "students" && <StudentsTab canCreate={canCreate} showPdChanges={isAdmin} />}
      {tab === "mark-codes" && <MarkCodesTab canEdit={isReferenceEditor} />}
      {tab === "users" && <UsersTab canCreate={canCreate} />}
      {tab === "calendar" && <CalendarTab canEdit={isReferenceEditor} canEditGroups={isReferenceEditor || isDeptHead} />}
      {tab === "journal" && <GroupJournalTab />}
      {tab === "import" && isAdmin && <ImportTab />}
      {tab === "debug" && isAdmin && <DebugTab />}
    </div>
  );
}
