import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { MIN_PASSWORD_LENGTH } from "../../constants/password";
import { useAuth } from "../../auth/useAuth";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { DeleteResult, DepartmentAdmin, SetPasswordResult, UserAdmin } from "../../api/types";
import { DEPARTMENT_REQUIRED_ROLES, DEPARTMENT_SCOPED_ROLES, ROLE, ROLE_LABELS, assignableRoles, inRoles, type RoleCode } from "../../constants/roles";
import { dialogs } from "../../utils/feedback";

function roleDisplay(u: UserAdmin): string {
  return ROLE_LABELS[u.role as RoleCode] || u.role;
}

function statusLabel(u: UserAdmin): string {
  if (!u.is_active) return "в архиве";
  if (u.is_locked) return "заблокирован";
  if (!u.has_password) return "нет пароля";
  if (u.must_change_password) return "ждёт смены пароля";
  return "активен";
}

const PAGE_SIZE = 15;

export default function UsersTab({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
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

  const [profileId, setProfileId] = useState<number | null>(null);
  // Архивные (удалённые/заблокированные насовсем оставленные в архиве)
  // пользователи не мешаются в основном списке — их можно найти отдельно.
  const [showArchived, setShowArchived] = useState(false);

  // Поиск/фильтр по роли и отделению — раньше список из полусотни
  // пользователей приходилось листать вручную (см. TODO.md 4).
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string | "all">("all");
  const [departmentFilter, setDepartmentFilter] = useState<number | "all">("all");

  const [justCreated, setJustCreated] = useState<SetPasswordResult | null>(null);
  // Итог удаления (например, «пользователь обезличен») показываем в самой вкладке: окно профиля к этому моменту закрыто.
  const [notice, setNotice] = useState<string | null>(null);

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
  const profileUser = rows.find((u) => u.id === profileId) ?? null;

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
            <input placeholder="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            <input placeholder="Логин" value={username} onChange={(e) => setUsername(e.target.value)} required />
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {(Object.entries(ROLE_LABELS) as [RoleCode, string][])
                .filter(([value]) => assignableRoles(me?.role).includes(value))
                .map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
            </select>
            {roleNeedsDepartment && (
              <select value={departmentId ?? ""} onChange={(e) => setDepartmentId(Number(e.target.value))}>
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
        <input placeholder="Поиск по ФИО" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="all">Все роли</option>
          {(Object.entries(ROLE_LABELS) as [RoleCode, string][]).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
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
                {canEdit ? (
                  <button className="link-btn" onClick={() => setProfileId(u.id)}>
                    {u.full_name}
                  </button>
                ) : (
                  u.full_name
                )}
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

      {profileUser && (
        <UserProfileModal
          user={profileUser}
          me={me}
          departments={departments}
          onClose={() => setProfileId(null)}
          onChanged={load}
          onNotice={setNotice}
        />
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

function UserProfileModal({
  user,
  me,
  departments,
  onClose,
  onChanged,
  onNotice,
}: {
  user: UserAdmin;
  me: { id: number; role: string } | null | undefined;
  departments: DepartmentAdmin[];
  onClose: () => void;
  onChanged: () => void;
  onNotice: (detail: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [editUsername, setEditUsername] = useState(user.username);
  const [editFullName, setEditFullName] = useState(user.full_name);
  const [editRole, setEditRole] = useState(user.role);
  const [editDepartmentId, setEditDepartmentId] = useState(user.department_id);

  const [customPasswordOpen, setCustomPasswordOpen] = useState(false);
  const [customPasswordValue, setCustomPasswordValue] = useState("");
  const [issuedPassword, setIssuedPassword] = useState<SetPasswordResult | null>(null);

  const isSelf = user.id === me?.id;
  const roleOptions = Array.from(new Set([user.role, ...assignableRoles(me?.role)]));
  useEscapeKey(onClose);

  async function saveProfile() {
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}`, {
        username: editUsername,
        full_name: editFullName,
        ...(isSelf ? {} : { role: editRole, department_id: editDepartmentId }),
      });
      setNotice("Сохранено");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function generatePassword() {
    setError(null);
    try {
      const res = await api.post<SetPasswordResult>(`/admin/users/${user.id}/set-password`, {});
      setIssuedPassword(res);
      setCustomPasswordOpen(false);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось задать пароль");
    }
  }

  async function submitCustomPassword(e: FormEvent) {
    e.preventDefault();
    if (customPasswordValue.length < MIN_PASSWORD_LENGTH) {
      setError(`Пароль должен быть не короче ${MIN_PASSWORD_LENGTH} символов`);
      return;
    }
    setError(null);
    try {
      const res = await api.post<SetPasswordResult>(`/admin/users/${user.id}/set-password`, {
        password: customPasswordValue,
      });
      setIssuedPassword(res);
      setCustomPasswordOpen(false);
      setCustomPasswordValue("");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось задать пароль");
    }
  }

  async function unlock() {
    setError(null);
    try {
      await api.post(`/admin/users/${user.id}/unlock`);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось снять блокировку");
    }
  }

  async function toggleActive() {
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}`, { is_active: !user.is_active });
      onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeUser() {
    if (!(await dialogs.confirm(`Удалить пользователя «${user.full_name}» насовсем?`, { confirmLabel: "Удалить", danger: true }))) return;
    setError(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/users/${user.id}`);
      onNotice(res.detail);
      onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={user.full_name} onClick={(e) => e.stopPropagation()}>
        <h3>{user.full_name}</h3>

        {error && <div className="error-text">{error}</div>}
        {notice && <div className="day-status submitted">{notice}</div>}

        {issuedPassword && (
          <div className="day-status submitted">
            Пароль для <b>{issuedPassword.username}</b>: <code>{issuedPassword.password}</code> — передайте его
            человеку лично, при первом входе система попросит его сменить.{" "}
            <button className="link-btn" onClick={() => setIssuedPassword(null)}>
              Скрыть
            </button>
          </div>
        )}

        <label>
          ФИО
          <input value={editFullName} onChange={(e) => setEditFullName(e.target.value)} />
        </label>
        <label>
          Логин
          <input value={editUsername} onChange={(e) => setEditUsername(e.target.value)} />
        </label>
        <label>
          Роль
          {isSelf || roleOptions.length <= 1 ? (
            <input value={ROLE_LABELS[user.role as RoleCode] ?? user.role} disabled />
          ) : (
            <select value={editRole} onChange={(e) => setEditRole(e.target.value)}>
              {roleOptions.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r as RoleCode] ?? r}
                </option>
              ))}
            </select>
          )}
        </label>

        {!isSelf && DEPARTMENT_REQUIRED_ROLES.includes(editRole) && !inRoles(me?.role, DEPARTMENT_SCOPED_ROLES) && (
          <label>
            Отделение
            <select value={editDepartmentId ?? ""} onChange={(e) => setEditDepartmentId(Number(e.target.value))}>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="actions">
          <button onClick={saveProfile}>Сохранить</button>
        </div>

        <hr />

        <p className="hint">Статус: {statusLabel(user)}</p>

        {customPasswordOpen ? (
          <form className="inline-form" onSubmit={submitCustomPassword}>
            <input
              type="text"
              placeholder="Свой пароль"
              value={customPasswordValue}
              onChange={(e) => setCustomPasswordValue(e.target.value)}
              minLength={MIN_PASSWORD_LENGTH}
              required
            />
            <button type="submit">Задать</button>
            <button type="button" className="link-btn" onClick={() => setCustomPasswordOpen(false)}>
              Отмена
            </button>
          </form>
        ) : (
          <div className="admin-row-actions">
            <button className="link-btn" onClick={generatePassword}>
              {user.has_password ? "Сбросить пароль" : "Выдать пароль"}
            </button>
            <button className="link-btn" onClick={() => setCustomPasswordOpen(true)}>
              Задать свой пароль
            </button>
            {user.is_locked && (
              <button className="link-btn" onClick={unlock}>
                Разблокировать
              </button>
            )}
          </div>
        )}

        <hr />

        <div className="actions">
          <button onClick={onClose}>Закрыть</button>
          {!isSelf && (
            <>
              <button className="link-btn" onClick={toggleActive}>
                {user.is_active ? "В архив" : "Вернуть из архива"}
              </button>
              {!user.is_active && (
                <button className="link-btn" onClick={removeUser}>
                  Удалить насовсем
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
