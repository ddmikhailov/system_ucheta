import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { CalendarDay } from "../../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthsAheadIso(n: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + n);
  return d.toISOString().slice(0, 10);
}

const DAY_TYPE_LABELS: Record<string, string> = {
  study_day: "Учебный день",
  weekend: "Выходной",
  holiday: "Праздник",
  vacation: "Каникулы",
};

export default function CalendarTab({ canEdit }: { canEdit: boolean }) {
  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(monthsAheadIso(3));
  const [rows, setRows] = useState<CalendarDay[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [newDate, setNewDate] = useState(todayIso());
  const [newType, setNewType] = useState("holiday");

  function load() {
    api
      .get<CalendarDay[]>(`/admin/calendar?date_from=${dateFrom}&date_to=${dateTo}`)
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(load, [dateFrom, dateTo]);

  async function addException() {
    setError(null);
    try {
      await api.put("/admin/calendar", { date: newDate, day_type: newType });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  return (
    <div>
      <p className="hint">
        По умолчанию будни — учебные дни, суббота и воскресенье — выходные; здесь задаются только исключения
        (праздники, каникулы, рабочие субботы). Если дата не отмечена ниже, действует правило по умолчанию.
      </p>
      {error && <div className="error-text">{error}</div>}

      <div className="toolbar">
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <span>—</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      </div>

      <table className="dash-table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Тип</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.date}>
              <td>{r.date}</td>
              <td>{DAY_TYPE_LABELS[r.day_type] ?? r.day_type}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={2}>Исключений в этом диапазоне нет.</td>
            </tr>
          )}
        </tbody>
      </table>

      {canEdit && (
        <div className="inline-form">
          <input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} />
          <select value={newType} onChange={(e) => setNewType(e.target.value)}>
            {Object.entries(DAY_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button onClick={addException}>Сохранить</button>
        </div>
      )}
    </div>
  );
}
