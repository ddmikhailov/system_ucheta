import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import type { DepartmentAdmin } from "../../api/types";

export default function DepartmentsTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<DepartmentAdmin[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      <table className="dash-table">
        <thead>
          <tr>
            <th>Название</th>
            <th>Активно</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td>{d.is_active ? "да" : "нет"}</td>
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
