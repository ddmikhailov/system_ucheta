import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { MIN_PASSWORD_LENGTH } from "../../constants/password";
import type { DeleteResult, DepartmentAdmin, SetPasswordResult, UserAdmin } from "../../api/types";
import { DEPARTMENT_REQUIRED_ROLES, DEPARTMENT_SCOPED_ROLES, ROLE_LABELS, assignableRoles, inRoles, type RoleCode } from "../../constants/roles";
import { dialogs } from "../../utils/feedback";
import { userStatusLabel as statusLabel } from "../../utils/userStatus";

/** Управление учётной записью: ФИО, логин, роль и отделение, пароль, блокировка, архив и
 * удаление. Раньше было окном поверх списка, теперь — вкладка «Управление» профиля. */
export default function UserManagePanel({
  user,
  me,
  departments,
  onChanged,
  onDeleted,
}: {
  user: UserAdmin;
  me: { id: number; role: string } | null | undefined;
  departments: DepartmentAdmin[];
  onChanged: () => void;
  /** Удалён или обезличен — профиля больше нет, итог показывается в списке. */
  onDeleted: (detail: string) => void;
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

  async function toggleActive() {
    setError(null);
    try {
      await api.patch(`/admin/users/${user.id}`, { is_active: !user.is_active });
      setNotice(user.is_active ? "Пользователь перенесён в архив" : "Пользователь возвращён из архива");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeUser() {
    if (!(await dialogs.confirm(`Удалить пользователя «${user.full_name}» насовсем?`, { confirmLabel: "Удалить", danger: true }))) return;
    setError(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/users/${user.id}`);
      onDeleted(res.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  return (
    <div className="manage-panel">
      <div className="add-block">
        <p className="add-block__title">Учётная запись</p>

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
              placeholder="Свой пароль" aria-label="Свой пароль"
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
          </div>
        )}

        <hr />

        <div className="actions">
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
