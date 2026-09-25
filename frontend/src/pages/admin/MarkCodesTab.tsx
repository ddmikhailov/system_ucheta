import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { MarkCodeAdmin } from "../../api/types";

type FlagField = "counts_as_present" | "is_excused" | "requires_document" | "is_active";

const FIELD_LABELS: Record<FlagField, string> = {
  counts_as_present: "считается присутствием",
  is_excused: "уважительная",
  requires_document: "требует документа",
  is_active: "активен",
};

export default function MarkCodesTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<MarkCodeAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  useScrollToTopOnChange(error);

  function load() {
    api.get<MarkCodeAdmin[]>("/admin/mark-codes").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(load, []);

  // Флаги пересчитывают отчётность задним числом (см. предупреждение выше и
  // TODO.md 4) — случайный клик мышью раньше применялся мгновенно без шанса
  // передумать.
  async function toggle(row: MarkCodeAdmin, field: FlagField) {
    const next = !row[field];
    if (
      !window.confirm(
        `Изменить флаг «${FIELD_LABELS[field]}» у кода «${row.code}» на «${next ? "да" : "нет"}»? Это пересчитает отчётность задним числом.`
      )
    ) {
      return;
    }
    try {
      await api.patch(`/admin/mark-codes/${row.id}`, { [field]: next });
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
