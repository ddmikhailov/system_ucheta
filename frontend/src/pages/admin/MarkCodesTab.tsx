import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { MarkCodeAdmin } from "../../api/types";

type FlagField = "counts_as_present" | "is_excused" | "requires_document" | "is_active";

export default function MarkCodesTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<MarkCodeAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api.get<MarkCodeAdmin[]>("/admin/mark-codes").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(load, []);

  async function toggle(row: MarkCodeAdmin, field: FlagField) {
    try {
      await api.patch(`/admin/mark-codes/${row.id}`, { [field]: !row[field] });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  return (
    <div>
      <p className="hint">
        Флаги пересчитывают всю отчётность сразу — правьте их осознанно. Например, если снять «считается
        присутствием» у кода «р» (практика), это изменит проценты во всех витринах и экспорте задним числом.
      </p>
      {error && <div className="error-text">{error}</div>}
      <table className="dash-table">
        <thead>
          <tr>
            <th>Код</th>
            <th>Значение</th>
            <th>Считается присутствием</th>
            <th>Уважительная</th>
            <th>Требует документа</th>
            <th>Активен</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.code}</td>
              <td>{r.name}</td>
              {(["counts_as_present", "is_excused", "requires_document", "is_active"] as FlagField[]).map((field) => (
                <td key={field}>
                  <input type="checkbox" checked={r[field]} disabled={!canEdit} onChange={() => toggle(r, field)} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
