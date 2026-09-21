import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { UserAdmin } from "../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function AssignCuratorModal({
  groupId,
  curators,
  onClose,
  onSaved,
}: {
  groupId: number;
  curators: UserAdmin[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [userId, setUserId] = useState<number | null>(curators[0]?.id ?? null);
  const [roleType, setRoleType] = useState("curator");
  const [startDate, setStartDate] = useState(todayIso());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (userId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/admin/curator-assignments", {
        study_group_id: groupId,
        user_id: userId,
        role_type: roleType,
        start_date: startDate,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Назначить куратора</h3>
        {curators.length === 0 ? (
          <p className="error-text">В отделении нет ни одного куратора или заместителя для назначения.</p>
        ) : (
          <>
            <label>
              Куратор
              <select value={userId ?? ""} onChange={(e) => setUserId(Number(e.target.value))}>
                {curators.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Роль
              <select value={roleType} onChange={(e) => setRoleType(e.target.value)}>
                <option value="curator">Основной куратор</option>
                <option value="deputy">Заместитель</option>
              </select>
            </label>
            <label>
              С даты
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
          </>
        )}
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button onClick={onClose}>Отмена</button>
          {curators.length > 0 && (
            <button onClick={save} disabled={busy || userId === null}>
              Сохранить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
