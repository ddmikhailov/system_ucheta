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
};

// Права роли dept_head одни и те же для всех — это просто разные подписи
// в интерфейсе для одной и той же должности по факту (см. обновление 1.1).
const DEPT_HEAD_TITLE_PRESETS = ["Зав. отделением", "Советник директора по воспитанию"];

function roleDisplay(u: UserAdmin): string {
  return u.display_title || ROLE_LABELS[u.role] || u.role;
}

function statusLabel(u: UserAdmin): string {
  if (!u.is_active) return "в архиве";
  if (u.is_locked) return "заблокирован";
  if (!u.has_password) return "нет пароля";
  if (u.must_change_password) return "ждёт смены пароля";
  return "активен";
}

export default function UsersTab({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const { user: me } = useAuth();
  const [rows, setRows] = useState<UserAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("curator");
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [displayTitle, setDisplayTitle] = useState(DEPT_HEAD_TITLE_PRESETS[0]);

  // Карточка с только что выданным паролем — показываем один раз, пока не закроют.
  const [issuedPassword, setIssuedPassword] = useState<SetPasswordResult | null>(null);
  // id пользователя, для которого сейчас открыта форма «свой пароль» (иначе — сразу генерируем).
  const [customPasswordFor, setCustomPasswordFor] = useState<number | null>(null);
  const [customPasswordValue, setCustomPasswordValue] = useState("");

  // id пользователя, который сейчас редактируется (логин/ФИО).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editUsername, setEditUsername] = useState("");
  const [editFullName, setEditFullName] = useState("");
  const [editDisplayTitle, setEditDisplayTitle] = useState(DEPT_HEAD_TITLE_PRESETS[0]);

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
      await api.post("/admin/users", {
        full_name: fullName, username, role, department_id: departmentId,
        display_title: role === "dept_head" && displayTitle !== DEPT_HEAD_TITLE_PRESETS[0] ? displayTitle : null,
      });
      setFullName("");
      setUsername("");
      setDisplayTitle(DEPT_HEAD_TITLE_PRESETS[0]);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать пользователя");
    } finally {
      setBusy(false);
    }
  }

  async function generatePassword(userId: number) {
    setError(null);
    try {
      const res = await api.post<SetPasswordResult>(`/admin/users/${userId}/set-password`, {});
      setIssuedPassword(res);
      setCustomPasswordFor(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось задать пароль");
    }
  }

  async function submitCustomPassword(userId: number, e: FormEvent) {
    e.preventDefault();
    if (customPasswordValue.length < 8) {
      setError("Пароль должен быть не короче 8 символов");
      return;
    }
    setError(null);
    try {
      const res = await api.post<SetPasswordResult>(`/admin/users/${userId}/set-password`, {
        password: customPasswordValue,
      });
      setIssuedPassword(res);
      setCustomPasswordFor(null);
      setCustomPasswordValue("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось задать пароль");
    }
  }

  async function unlock(userId: number) {
    setError(null);
    try {
      await api.post(`/admin/users/${userId}/unlock`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось снять блокировку");
    }
  }

  function startEdit(u: UserAdmin) {
    setEditingId(u.id);
    setEditUsername(u.username);
    setEditFullName(u.full_name);
    setEditDisplayTitle(u.display_title || DEPT_HEAD_TITLE_PRESETS[0]);
  }

  async function saveEdit(userId: number, role: string) {
    setError(null);
    try {
      await api.patch(`/admin/users/${userId}`, {
        username: editUsername, full_name: editFullName,
        ...(role === "dept_head" ? { display_title: editDisplayTitle === DEPT_HEAD_TITLE_PRESETS[0] ? "" : editDisplayTitle } : {}),
      });
      setEditingId(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function toggleActive(u: UserAdmin) {
    setError(null);
    try {
      await api.patch(`/admin/users/${u.id}`, { is_active: !u.is_active });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeUser(u: UserAdmin) {
    if (!window.confirm(`Удалить пользователя «${u.full_name}» насовсем?`)) return;
    setError(null);
    setNotice(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/users/${u.id}`);
      setNotice(res.detail);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  async function toggleLeadershipDigest(user: UserAdmin) {
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}/leadership-digest`, {
        receives_leadership_digest: !user.receives_leadership_digest,
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  return (
    <div>
      {error && <div className="error-text">{error}</div>}

      {issuedPassword && (
        <div className="day-status submitted">
          Пароль для <b>{issuedPassword.username}</b>: <code>{issuedPassword.password}</code> — передайте его
          человеку лично, при первом входе система попросит его сменить.{" "}
          <button className="link-btn" onClick={() => setIssuedPassword(null)}>
            Скрыть
          </button>
        </div>
      )}

      {notice && (
        <div className="day-status submitted">
          {notice} <button className="link-btn" onClick={() => setNotice(null)}>Скрыть</button>
        </div>
      )}

      <table className="dash-table">
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Логин</th>
            <th>Роль</th>
            <th>Статус</th>
            <th title="Получает пятничный дайджест руководству из концепции — это не роль с правами, а просто отметка получателя">
              Дайджест рук-ва
            </th>
            {canEdit && <th>Управление</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              {editingId === u.id ? (
                <>
                  <td>
                    <input value={editFullName} onChange={(e) => setEditFullName(e.target.value)} />
                  </td>
                  <td>
                    <input value={editUsername} onChange={(e) => setEditUsername(e.target.value)} />
                  </td>
                </>
              ) : (
                <>
                  <td>{u.full_name}</td>
                  <td>{u.username}</td>
                </>
              )}
              <td>
                {editingId === u.id && u.role === "dept_head" ? (
                  <select value={editDisplayTitle} onChange={(e) => setEditDisplayTitle(e.target.value)}>
                    {DEPT_HEAD_TITLE_PRESETS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                ) : (
                  roleDisplay(u)
                )}
              </td>
              <td>{statusLabel(u)}</td>
              <td>
                <input
                  type="checkbox"
                  checked={u.receives_leadership_digest}
                  disabled={!canEdit}
                  onChange={() => toggleLeadershipDigest(u)}
                />
              </td>
              {canEdit && (
                <td className="admin-row-actions">
                  {editingId === u.id ? (
                    <>
                      <button className="link-btn" onClick={() => saveEdit(u.id, u.role)}>
                        Сохранить
                      </button>
                      <button className="link-btn" onClick={() => setEditingId(null)}>
                        Отмена
                      </button>
                    </>
                  ) : (
                    <button className="link-btn" onClick={() => startEdit(u)}>
                      Изменить логин/ФИО
                    </button>
                  )}

                  {customPasswordFor === u.id ? (
                    <form className="inline-form" onSubmit={(e) => submitCustomPassword(u.id, e)}>
                      <input
                        type="text"
                        placeholder="Свой пароль"
                        value={customPasswordValue}
                        onChange={(e) => setCustomPasswordValue(e.target.value)}
                        minLength={8}
                        required
                      />
                      <button type="submit">Задать</button>
                      <button type="button" className="link-btn" onClick={() => setCustomPasswordFor(null)}>
                        Отмена
                      </button>
                    </form>
                  ) : (
                    <>
                      <button className="link-btn" onClick={() => generatePassword(u.id)}>
                        {u.has_password ? "Сбросить пароль" : "Выдать пароль"}
                      </button>
                      <button className="link-btn" onClick={() => setCustomPasswordFor(u.id)}>
                        Задать свой пароль
                      </button>
                    </>
                  )}

                  {u.is_locked && (
                    <button className="link-btn" onClick={() => unlock(u.id)}>
                      Разблокировать
                    </button>
                  )}

                  {u.id !== me?.id && (
                    <>
                      <button className="link-btn" onClick={() => toggleActive(u)}>
                        {u.is_active ? "В архив" : "Вернуть из архива"}
                      </button>
                      {!u.is_active && (
                        <button className="link-btn" onClick={() => removeUser(u)}>
                          Удалить насовсем
                        </button>
                      )}
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

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
          {role === "dept_head" && (
            <select value={displayTitle} onChange={(e) => setDisplayTitle(e.target.value)}>
              {DEPT_HEAD_TITLE_PRESETS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          )}
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
    </div>
  );
}
