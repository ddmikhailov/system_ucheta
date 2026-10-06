import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import { Link, useLocation } from "react-router-dom";
import type { DepartmentAdmin, SetPasswordResult, UserAdmin } from "../../api/types";
import { DEPARTMENT_REQUIRED_ROLES, DEPARTMENT_SCOPED_ROLES, ROLE, ROLE_LABELS, assignableRoles, inRoles, type RoleCode } from "../../constants/roles";
import { userStatusLabel as statusLabel } from "../../utils/userStatus";

function roleDisplay(u: UserAdmin): string {
  return ROLE_LABELS[u.role as RoleCode] || u.role;
}


const PAGE_SIZE = 15;

export default function UsersTab({ canCreate }: { canCreate: boolean }) {
  const { user: me } = useAuth();
  const [rows, setRows] = useState<UserAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  useScrollToTopOnChange(error);
  const [page, setPage] = useState(0);

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<string>(ROLE.CURATOR);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  // Архивные (удалённые/заблокированные насовсем оставленные в архиве)
  // пользователи не мешаются в основном списке — их можно найти отдельно.
  const [showArchived, setShowArchived] = useState(false);

  // Поиск/фильтр по роли и отделению — раньше список из полусотни
  // пользователей приходилось листать вручную (см. TODO.md 4).
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string | "all">("all");
  const [departmentFilter, setDepartmentFilter] = useState<number | "all">("all");

  const [justCreated, setJustCreated] = useState<SetPasswordResult | null>(null);
  // Итог удаления из профиля (например, «пользователь обезличен») приходит сюда через состояние перехода.
  const location = useLocation();
  const [notice, setNotice] = useState<string | null>((location.state as { notice?: string } | null)?.notice ?? null);

  function load() {
    api.get<UserAdmin[]>("/admin/users").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
    api.get<DepartmentAdmin[]>("/admin/departments").then((all) => {
      // Зав. отделением и тьютор создают только в своём отделении.
      const ds = inRoles(me?.role, DEPARTMENT_SCOPED_ROLES) ? all.filter((d) => d.name === me?.department_name) : all;
      setDepartments(ds);
      if (ds.length > 0 && departmentId === null) setDepartmentId(ds[0].id);
    });
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  const roleNeedsDepartment = DEPARTMENT_REQUIRED_ROLES.includes(role);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setJustCreated(null);
    let created: UserAdmin;
    try {
      created = await api.post<UserAdmin>("/admin/users", {
        full_name: fullName,
        username,
        role,
        department_id: roleNeedsDepartment ? departmentId : null,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать пользователя");
      setBusy(false);
      return;
    }
    setFullName("");
    setUsername("");
    try {
      // Сразу выдаём пароль новому пользователю — раньше для этого приходилось
      // отдельно открывать его профиль (см. TODO.md 4).
      setJustCreated(await api.post<SetPasswordResult>(`/admin/users/${created.id}/set-password`, {}));
    } catch (err) {
      // Пользователь уже создан: список обновляем в любом случае, а ошибку объясняем так, чтобы не создали его второй раз.
      const reason = err instanceof ApiError ? ` (${err.message})` : "";
      setError(`Пользователь «${created.full_name}» создан, но пароль выдать не удалось${reason} — выдайте его в профиле пользователя.`);
    } finally {
      load();
      setBusy(false);
    }
  }

  const searchedRows = rows.filter((u) => {
    if (searchQuery.trim() && !u.full_name.toLowerCase().includes(searchQuery.trim().toLowerCase())) return false;
    if (roleFilter !== "all" && u.role !== roleFilter) return false;
    if (departmentFilter !== "all" && u.department_id !== departmentFilter) return false;
    return true;
  });
  const visibleRows = showArchived ? searchedRows : searchedRows.filter((u) => u.is_active);
  const archivedCount = searchedRows.length - searchedRows.filter((u) => u.is_active).length;
  const pageCount = Math.max(1, Math.ceil(visibleRows.length / PAGE_SIZE));
  // Поиск/фильтр сокращают список: без этой поправки, стоя на странице 2, можно было увидеть пустую таблицу.
  const currentPage = Math.min(page, pageCount - 1);
  const pageRows = visibleRows.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice}{" "}
          <button className="link-btn" onClick={() => setNotice(null)}>
            Скрыть
          </button>
        </div>
      )}

      {justCreated && (
        <div className="day-status submitted">
          Пароль для <b>{justCreated.username}</b>: <code>{justCreated.password}</code>{" "}
          <button
            className="link-btn"
            onClick={() => navigator.clipboard?.writeText(justCreated.password)}
          >
            Скопировать
          </button>{" "}
          <button className="link-btn" onClick={() => setJustCreated(null)}>
            Скрыть
          </button>
        </div>
      )}

      {canCreate && (
        <div className="add-block">
          <p className="add-block__title">Добавить пользователя</p>
          <form className="inline-form" onSubmit={handleCreate}>
            <input placeholder="ФИО" aria-label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            <input placeholder="Логин" aria-label="Логин" value={username} onChange={(e) => setUsername(e.target.value)} required />
            <select aria-label="Роль" value={role} onChange={(e) => setRole(e.target.value)}>
              {(Object.entries(ROLE_LABELS) as [RoleCode, string][])
                .filter(([value]) => assignableRoles(me?.role).includes(value))
                .map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
            </select>
            {roleNeedsDepartment && (
              <select aria-label="Отделение" value={departmentId ?? ""} onChange={(e) => setDepartmentId(Number(e.target.value))}>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            )}
            <button type="submit" disabled={busy}>
              Добавить пользователя
            </button>
          </form>
        </div>
      )}

      <div className="toolbar">
        <input placeholder="Поиск по ФИО" aria-label="Поиск по ФИО" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        <select aria-label="Фильтр по роли" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="all">Все роли</option>
          {(Object.entries(ROLE_LABELS) as [RoleCode, string][]).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Фильтр по отделению"
          value={departmentFilter}
          onChange={(e) => setDepartmentFilter(e.target.value === "all" ? "all" : Number(e.target.value))}
        >
          <option value="all">Все отделения</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      <table className="dash-table">
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Логин</th>
            <th>Роль</th>
            <th>Отделение</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {pageRows.map((u) => (
            <tr key={u.id}>
              <td>
                <Link className="link-btn" to={`/admin/users/${u.id}`}>
                  {u.full_name}
                </Link>
              </td>
              <td>{u.username}</td>
              <td>{roleDisplay(u)}</td>
              <td>{departments.find((d) => d.id === u.department_id)?.name ?? "—"}</td>
              <td>{statusLabel(u)}</td>
            </tr>
          ))}
          {pageRows.length === 0 && (
            <tr>
              <td colSpan={5}>Пользователей нет.</td>
            </tr>
          )}
        </tbody>
      </table>

      {pageCount > 1 && (
        <div className="toolbar">
          <button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
            ← Назад
          </button>
          <span>
            Страница {currentPage + 1} из {pageCount}
          </span>
          <button disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>
            Вперёд →
          </button>
        </div>
      )}

      {archivedCount > 0 && (
        <p className="hint archive-toggle">
          <button
            className="link-btn"
            onClick={() => {
              setShowArchived((v) => !v);
              setPage(0);
            }}
          >
            {showArchived ? "Скрыть архив" : `Архив (${archivedCount})`}
          </button>
        </p>
      )}
    </div>
  );
}
