import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { CalendarDay, GroupCalendarOverride, StudyGroupAdmin } from "../../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthsAheadIso(n: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + n);
  return d.toISOString().slice(0, 10);
}

function formatDateRu(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

const DAY_TYPE_LABELS: Record<string, string> = {
  study_day: "Учебный день",
  weekend: "Выходной",
  holiday: "Праздник",
  vacation: "Каникулы",
  remote: "ЭФО (дистанционно)",
};

export default function CalendarTab({ canEdit }: { canEdit: boolean }) {
  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(monthsAheadIso(3));
  const [rows, setRows] = useState<CalendarDay[]>([]);
  const [error, setError] = useState<string | null>(null);
  useScrollToTopOnChange(error);

  const [newDate, setNewDate] = useState(todayIso());
  const [newDateTo, setNewDateTo] = useState("");
  const [newType, setNewType] = useState("holiday");
  const [bulkBusy, setBulkBusy] = useState(false);

  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [overrideGroupId, setOverrideGroupId] = useState<number | null>(null);
  const [overrides, setOverrides] = useState<GroupCalendarOverride[]>([]);
  const [overrideDate, setOverrideDate] = useState(todayIso());
  const [overrideType, setOverrideType] = useState("remote");

  function load() {
    api
      .get<CalendarDay[]>(`/admin/calendar?date_from=${dateFrom}&date_to=${dateTo}`)
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(load, [dateFrom, dateTo]);

  useEffect(() => {
    api.get<StudyGroupAdmin[]>("/admin/groups").then((allGroups) => {
      const gs = allGroups.filter((g) => g.is_active);
      setGroups(gs);
      if (gs.length > 0 && overrideGroupId === null) setOverrideGroupId(gs[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function loadOverrides() {
    if (overrideGroupId === null) return;
    api
      .get<GroupCalendarOverride[]>(
        `/admin/calendar/group-overrides?study_group_id=${overrideGroupId}&date_from=${dateFrom}&date_to=${dateTo}`
      )
      .then(setOverrides)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(loadOverrides, [overrideGroupId, dateFrom, dateTo]);

  // Каникулы — это диапазон в несколько недель, а не один день; раньше
  // приходилось добавлять их по одной дате (см. TODO.md 4).
  function datesBetween(from: string, to: string): string[] {
    const result: string[] = [];
    const cur = new Date(from + "T00:00:00");
    const end = new Date(to + "T00:00:00");
    while (cur <= end) {
      result.push(cur.toISOString().slice(0, 10));
      cur.setDate(cur.getDate() + 1);
    }
    return result;
  }

  async function addException() {
    setError(null);
    const dates = newDateTo && newDateTo > newDate ? datesBetween(newDate, newDateTo) : [newDate];
    setBulkBusy(true);
    try {
      for (const date of dates) {
        await api.put("/admin/calendar", { date, day_type: newType });
      }
      setNewDateTo("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setBulkBusy(false);
    }
  }

  async function removeException(date: string) {
    setError(null);
    try {
      await api.delete(`/admin/calendar/${date}`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  async function addGroupOverride() {
    if (overrideGroupId === null) return;
    setError(null);
    try {
      await api.put("/admin/calendar/group-overrides", {
        study_group_id: overrideGroupId,
        date: overrideDate,
        day_type: overrideType,
      });
      loadOverrides();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeGroupOverride(date: string) {
    if (overrideGroupId === null) return;
    setError(null);
    try {
      await api.delete(`/admin/calendar/group-overrides?study_group_id=${overrideGroupId}&date=${date}`);
      loadOverrides();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  return (
    <div>
      <p className="hint">
        По умолчанию будни — учебные дни, воскресенье — выходной; суббота учебная только у 1 курса, у остальных
        курсов — выходной. Здесь задаются исключения для всего колледжа (праздники, каникулы) и отдельно — для
        конкретной группы (например, день ЭФО или рабочая суббота вне общего правила).
      </p>
      {error && <div className="error-text">{error}</div>}

      <div className="toolbar">
        <button
          className="link-btn"
          onClick={() => {
            setDateFrom(monthsAheadIso(-3));
            setDateTo(todayIso());
          }}
          title="Посмотреть прошедший период"
        >
          ← Прошедшие
        </button>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <span>—</span>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      </div>

      <h4>Общий календарь (весь колледж)</h4>
      <table className="dash-table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Тип</th>
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.date}>
              <td>{formatDateRu(r.date)}</td>
              <td>{DAY_TYPE_LABELS[r.day_type] ?? r.day_type}</td>
              {canEdit && (
                <td>
                  <button className="link-btn" onClick={() => removeException(r.date)}>
                    Убрать (вернуть по умолчанию)
                  </button>
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={canEdit ? 3 : 2}>Исключений в этом диапазоне нет.</td>
            </tr>
          )}
        </tbody>
      </table>

      {canEdit && (
        <div className="inline-form">
          <input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} title="Дата (начало диапазона)" />
          <span>—</span>
          <input
            type="date"
            value={newDateTo}
            onChange={(e) => setNewDateTo(e.target.value)}
            title="Конец диапазона — необязательно, для каникул на несколько дней"
          />
          <select value={newType} onChange={(e) => setNewType(e.target.value)}>
            {Object.entries(DAY_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button onClick={addException} disabled={bulkBusy}>
            {bulkBusy ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
      )}

      <h4>Исключения по конкретной группе</h4>
      <div className="toolbar">
        <select value={overrideGroupId ?? ""} onChange={(e) => setOverrideGroupId(Number(e.target.value))}>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.code} (курс {g.course})
            </option>
          ))}
        </select>
      </div>

      <table className="dash-table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Тип</th>
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {overrides.map((r) => (
            <tr key={r.date}>
              <td>{formatDateRu(r.date)}</td>
              <td>{DAY_TYPE_LABELS[r.day_type] ?? r.day_type}</td>
              {canEdit && (
                <td>
                  <button className="link-btn" onClick={() => removeGroupOverride(r.date)}>
                    Убрать (вернуть по умолчанию)
                  </button>
                </td>
              )}
            </tr>
          ))}
          {overrides.length === 0 && (
            <tr>
              <td colSpan={canEdit ? 3 : 2}>У этой группы нет отдельных исключений в этом диапазоне.</td>
            </tr>
          )}
        </tbody>
      </table>

      {canEdit && (
        <div className="inline-form">
          <input type="date" value={overrideDate} onChange={(e) => setOverrideDate(e.target.value)} />
          <select value={overrideType} onChange={(e) => setOverrideType(e.target.value)}>
            {Object.entries(DAY_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button onClick={addGroupOverride}>Сохранить для группы</button>
        </div>
      )}
    </div>
  );
}
