import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import type { DepartmentAdmin, InvitationRead, UserAdmin } from "../../api/types";

const ROLE_LABELS: Record<string, string> = {
  curator: "Куратор",
  deputy_curator: "Заместитель куратора",
  dept_head: "Зав. отделением",
  edu_department: "Воспитательный отдел",
  admin: "Администратор",
};

export default function UsersTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<UserAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [invitation, setInvitation] = useState<{ userId: number; link: string } | null>(null);

  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("curator");
  const [departmentId, setDepartmentId] = useState<number | null>(null);

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

  async function issueInvitation(userId: number) {
    setError(null);
    try {
      const res = await api.post<InvitationRead>(`/admin/users/${userId}/invitations`);
      setInvitation({ userId, link: `${window.location.origin}${res.invitation_url_path}` });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось выпустить приглашение");
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

      {invitation && (
        <div className="day-status submitted">
          Ссылка-приглашение (передайте лично, действует ограниченное время): <code>{invitation.link}</code>
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
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              <td>{u.full_name}</td>
              <td>{u.username}</td>
              <td>{ROLE_LABELS[u.role] ?? u.role}</td>
              <td>{u.has_password ? "активирован" : "ждёт приглашения"}</td>
              <td>
                <input
                  type="checkbox"
                  checked={u.receives_leadership_digest}
                  disabled={!canEdit}
                  onChange={() => toggleLeadershipDigest(u)}
                />
              </td>
              {canEdit && (
                <td>
                  {!u.has_password && (
                    <button className="link-btn" onClick={() => issueInvitation(u.id)}>
                      Выдать ссылку
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {canEdit && (
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
