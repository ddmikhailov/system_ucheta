import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import type { DeleteResult, DepartmentAdmin, SetPasswordResult, UserAdmin } from "../../api/types";

const ROLE_LABELS: Record<string, string> = {
  curator: "Куратор",
  deputy_curator: "Заместитель куратора",
  dept_head: "Зав. отделением",
  edu_department: "Воспитательный отдел",
  admin: "Администратор",
  tutor: "Тьютор",
};

function roleDisplay(u: UserAdmin): string {
  return ROLE_LABELS[u.role] || u.role;
}

// Менять роль могут только администратор и зав. отделением (обновление
// 1.3) — зеркалит ограничение на бэкенде (_assert_can_assign_role в
// admin.py). Зав. отделением не может назначить роль выше своей.
function assignableRoles(myRole: string | undefined): string[] {
  if (myRole === "admin") return Object.keys(ROLE_LABELS);
  if (myRole === "dept_head") return ["curator", "deputy_curator", "dept_head"];
  return [];
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
  const [page, setPage] = useState(0);

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("curator");
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const [profileId, setProfileId] = useState<number | null>(null);

  function load() {
    api.get<UserAdmin[]>("/admin/users").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
    api.get<DepartmentAdmin[]>("/admin/departments").then((ds) => {
      setDepartments(ds);
      if (ds.length > 0 && departmentId === null) setDepartmentId(ds[0].id);
    });
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/admin/users", { full_name: fullName, username, role, department_id: departmentId });
      setFullName("");
      setUsername("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать пользователя");
    } finally {
      setBusy(false);
    }
  }

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const profileUser = rows.find((u) => u.id === profileId) ?? null;

  return (
    <div>
      {error && <div className="error-text">{error}</div>}

      <table className="dash-table">
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Логин</th>
            <th>Роль</th>
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
              <td>{statusLabel(u)}</td>
            </tr>
          ))}
          {pageRows.length === 0 && (
            <tr>
              <td colSpan={4}>Пользователей нет.</td>
            </tr>
          )}
        </tbody>
      </table>

      {pageCount > 1 && (
        <div className="toolbar">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            ← Назад
          </button>
          <span>
            Страница {page + 1} из {pageCount}
          </span>
          <button disabled={page >= pageCount - 1} onClick={() => setPage((p) => p + 1)}>
            Вперёд →
          </button>
        </div>
      )}

      {canCreate && (
        <form className="inline-form" onSubmit={handleCreate}>
          <input placeholder="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          <input placeholder="Логин" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select value={departmentId ?? ""} onChange={(e) => setDepartmentId(Number(e.target.value))}>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy}>
            Добавить пользователя
          </button>
        </form>
      )}

      {profileUser && (
        <UserProfileModal
          user={profileUser}
          me={me}
          onClose={() => setProfileId(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

function UserProfileModal({
  user,
  me,
  onClose,
  onChanged,
}: {
  user: UserAdmin;
  me: { id: number; role: string } | null | undefined;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [editUsername, setEditUsername] = useState(user.username);
  const [editFullName, setEditFullName] = useState(user.full_name);
  const [editRole, setEditRole] = useState(user.role);

  const [customPasswordOpen, setCustomPasswordOpen] = useState(false);
  const [customPasswordValue, setCustomPasswordValue] = useState("");
  const [issuedPassword, setIssuedPassword] = useState<SetPasswordResult | null>(null);

  const isSelf = user.id === me?.id;
  const roleOptions = Array.from(new Set([user.role, ...assignableRoles(me?.role)]));

  async function saveProfile() {
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}`, {
        username: editUsername,
        full_name: editFullName,
        ...(isSelf ? {} : { role: editRole }),
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
    if (customPasswordValue.length < 8) {
      setError("Пароль должен быть не короче 8 символов");
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
    if (!window.confirm(`Удалить пользователя «${user.full_name}» насовсем?`)) return;
    setError(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/users/${user.id}`);
      setNotice(res.detail);
      onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  async function toggleLeadershipDigest() {
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}/leadership-digest`, {
        receives_leadership_digest: !user.receives_leadership_digest,
      });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
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
            <input value={ROLE_LABELS[user.role] ?? user.role} disabled />
          ) : (
            <select value={editRole} onChange={(e) => setEditRole(e.target.value)}>
              {roleOptions.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r] ?? r}
                </option>
              ))}
            </select>
          )}
        </label>

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
              minLength={8}
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

        <label style={{ marginTop: "10px" }}>
          <input
            type="checkbox"
            checked={user.receives_leadership_digest}
            onChange={toggleLeadershipDigest}
          />{" "}
          Получает пятничный дайджест руководству
        </label>

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
