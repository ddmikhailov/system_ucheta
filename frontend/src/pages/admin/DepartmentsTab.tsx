import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { DepartmentAdmin } from "../../api/types";

export default function DepartmentsTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<DepartmentAdmin[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  useScrollToTopOnChange(error);
  const [busy, setBusy] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  function load() {
    api.get<DepartmentAdmin[]>("/admin/departments").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/admin/departments", { name });
      setName("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(d: DepartmentAdmin) {
    setEditingId(d.id);
    setEditName(d.name);
  }

  async function saveEdit(id: number) {
    setError(null);
    try {
      await api.patch(`/admin/departments/${id}`, { name: editName });
      setEditingId(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function toggleActive(d: DepartmentAdmin) {
    if (d.is_active && !window.confirm(`Архивировать отделение «${d.name}»? Группы и пользователи в нём не удаляются.`)) return;
    setError(null);
    try {
      await api.patch(`/admin/departments/${d.id}`, { is_active: !d.is_active });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      <table className="dash-table">
        <thead>
          <tr>
            <th>Название</th>
            <th>Активно</th>
            {canEdit && <th>Управление</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td>
                {editingId === d.id ? (
                  <input value={editName} onChange={(e) => setEditName(e.target.value)} />
                ) : (
                  d.name
                )}
              </td>
              <td>{d.is_active ? "да" : "нет"}</td>
              {canEdit && (
                <td className="admin-row-actions">
                  {editingId === d.id ? (
                    <>
                      <button className="link-btn" onClick={() => saveEdit(d.id)}>
                        Сохранить
                      </button>
                      <button className="link-btn" onClick={() => setEditingId(null)}>
                        Отмена
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="link-btn" onClick={() => startEdit(d)}>
                        Переименовать
                      </button>
                      <button className="link-btn" onClick={() => toggleActive(d)}>
                        {d.is_active ? "В архив" : "Вернуть из архива"}
                      </button>
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {canEdit && (
        <form className="inline-form" onSubmit={handleCreate}>
          <input placeholder="Новое отделение" value={name} onChange={(e) => setName(e.target.value)} required />
          <button type="submit" disabled={busy}>
            Добавить
          </button>
        </form>
      )}
    </div>
  );
}
