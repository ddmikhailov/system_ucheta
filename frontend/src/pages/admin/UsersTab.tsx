import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import type { DepartmentAdmin, SetPasswordResult, UserAdmin } from "../../api/types";

const ROLE_LABELS: Record<string, string> = {
  curator: "Куратор",
  deputy_curator: "Заместитель куратора",
  dept_head: "Зав. отделением",
  edu_department: "Воспитательный отдел",
  admin: "Администратор",
};

function statusLabel(u: UserAdmin): string {
  if (u.is_locked) return "заблокирован";
  if (!u.has_password) return "нет пароля";
  if (u.must_change_password) return "ждёт смены пароля";
  return "активен";
}

export default function UsersTab({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const [rows, setRows] = useState<UserAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("curator");
  const [departmentId, setDepartmentId] = useState<number | null>(null);

  // Карточка с только что выданным паролем — показываем один раз, пока не закроют.
  const [issuedPassword, setIssuedPassword] = useState<SetPasswordResult | null>(null);
  // id пользователя, для которого сейчас открыта форма «свой пароль» (иначе — сразу генерируем).
  const [customPasswordFor, setCustomPasswordFor] = useState<number | null>(null);
  const [customPasswordValue, setCustomPasswordValue] = useState("");

  // id пользователя, который сейчас редактируется (логин/ФИО).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editUsername, setEditUsername] = useState("");
  const [editFullName, setEditFullName] = useState("");

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
  }

  async function saveEdit(userId: number) {
    setError(null);
    try {
      await api.patch(`/admin/users/${userId}`, { username: editUsername, full_name: editFullName });
      setEditingId(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
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
              <td>{ROLE_LABELS[u.role] ?? u.role}</td>
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
                      <button className="link-btn" onClick={() => saveEdit(u.id)}>
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
