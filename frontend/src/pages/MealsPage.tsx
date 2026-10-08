import { useEffect, useMemo, useState } from "react";
import { api, ApiError, downloadFile } from "../api/client";
import type { MealOverview, MealOverviewRow } from "../api/types";
import ResultsBar from "../components/dashboards/ResultsBar";
import SortHeader from "../components/dashboards/SortHeader";
import GroupMealsPanel from "../components/meals/GroupMealsPanel";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { addDaysIso, formatDayMonthRu, formatDueShort, formatLocalDateTime, todayIso } from "../utils/date";
import { filterByQuery } from "../utils/searchMatch";
import { nextSort, sortRows } from "../utils/tableView";
import type { SortState } from "../utils/tableView";

const STATUS_TEXT: Record<MealOverviewRow["status"], string> = {
  submitted: "подано",
  pending: "ещё не подано",
  forecast: "по прогнозу",
};

type Status = MealOverviewRow["status"];

/** Понедельник недели, на которую сейчас подают питание: по умолчанию — следующая неделя. */
function nextMonday(): string {
  const today = todayIso();
  const [y, m, d] = today.split("-").map(Number);
  const weekday = (new Date(y, m - 1, d).getDay() + 6) % 7; // 0 — понедельник
  return addDaysIso(today, 7 - weekday);
}

/** Вкладка «Питание»: своды питающихся по группам и отделениям на неделю — подано куратором или прогноз. */
export default function MealsPage() {
  const [week, setWeek] = useState(nextMonday);
  const [data, setData] = useState<MealOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState<number | "all">("all");
  const [course, setCourse] = useState<number | "all">("all");
  const [status, setStatus] = useState<Status | "all">("all");
  const [sort, setSort] = useState<SortState<string> | null>(null);
  const [openGroup, setOpenGroup] = useState<MealOverviewRow | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Загрузка при смене недели: setState — после await.
    // oxlint-disable-next-line react/set-state-in-effect
    setLoading(true);
    api
      .get<MealOverview>(`/meals/overview?week_start=${week}`)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Не удалось загрузить свод");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [week, reloadKey]);

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const dates = useMemo(() => data?.dates ?? [], [data]);
  const departments = useMemo(() => {
    const byId = new Map<number, string>();
    for (const r of rows) byId.set(r.department_id, r.department_name);
    return [...byId].sort((a, b) => a[1].localeCompare(b[1], "ru"));
  }, [rows]);
  const courses = useMemo(() => Array.from(new Set(rows.map((r) => r.course))).sort((a, b) => a - b), [rows]);

  const filtered = query.trim() !== "" || department !== "all" || course !== "all" || status !== "all";
  const visible = useMemo(() => {
    let list = rows;
    if (department !== "all") list = list.filter((r) => r.department_id === department);
    if (course !== "all") list = list.filter((r) => r.course === course);
    if (status !== "all") list = list.filter((r) => r.status === status);
    list = filterByQuery(list, query, (r) => `${r.code} ${r.curator_name ?? "нет куратора"}`);
    const getters: Record<string, (r: MealOverviewRow) => string | number | null> = {
      code: (r) => r.code, course: (r) => r.course, department: (r) => r.department_name,
      curator: (r) => r.curator_name, eaters: (r) => r.eaters, percent: (r) => r.attendance_percent, status: (r) => r.status,
    };
    for (const d of dates) getters[`day:${d}`] = (r) => r.days.find((x) => x.date === d)?.count ?? null;
    return sortRows(list, sort, getters);
  }, [rows, dates, department, course, status, query, sort]);

  const totals = useMemo(() => {
    const sums: Record<string, number> = {};
    for (const r of visible) for (const d of r.days) sums[d.date] = (sums[d.date] ?? 0) + d.count;
    return sums;
  }, [visible]);
  const forecastCount = rows.filter((r) => r.status === "forecast").length;
  const pendingCount = rows.filter((r) => r.status === "pending").length;

  function reset() {
    setQuery("");
    setDepartment("all");
    setCourse("all");
    setStatus("all");
  }

  function exportExcel() {
    setExportError(null);
    const dep = department === "all" ? "" : `&department_id=${department}`;
    downloadFile(`/meals/export?week_start=${week}${dep}`, `pitanie_${week}.xlsx`).catch((err) =>
      setExportError(err instanceof ApiError ? err.message : "Не удалось скачать файл"),
    );
  }

  const last = addDaysIso(week, 5);
  return (
    <div className="meals-overview">
      <div className="toolbar">
        <button type="button" className="btn-secondary" onClick={() => setWeek(addDaysIso(week, -7))} aria-label="Предыдущая неделя">‹</button>
        <strong>Неделя {formatDayMonthRu(week)}–{formatDayMonthRu(last)}</strong>
        <button type="button" className="btn-secondary" onClick={() => setWeek(addDaysIso(week, 7))} aria-label="Следующая неделя">›</button>
        <button type="button" className="link-btn" onClick={() => setReloadKey((k) => k + 1)} title="Запросить данные заново">Обновить</button>
        <button type="button" className="link-btn" onClick={exportExcel}>Экспорт в Excel</button>
      </div>
      {exportError && <div className="error-text">{exportError}</div>}
      {error && <div className="error-text">{error}</div>}
      {loading && <p className="hint">Загрузка…</p>}

      {data && (
        <p className="hint">
          Срок подачи кураторами — {formatLocalDateTime(data.deadline)}. Подано: {rows.length - forecastCount - pendingCount} из {rows.length};
          {" "}ещё не подали: {pendingCount}; по прогнозу: {forecastCount}.
        </p>
      )}

      <div className="toolbar toolbar--filters">
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Группа или куратор" aria-label="Поиск по группе или куратору" />
        {departments.length > 1 && (
          <select aria-label="Отделение" value={department} onChange={(e) => setDepartment(e.target.value === "all" ? "all" : Number(e.target.value))}>
            <option value="all">Все отделения</option>
            {departments.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </select>
        )}
        <select aria-label="Курс" value={course} onChange={(e) => setCourse(e.target.value === "all" ? "all" : Number(e.target.value))}>
          <option value="all">Все курсы</option>
          {courses.map((c) => (
            <option key={c} value={c}>Курс {c}</option>
          ))}
        </select>
        <select aria-label="Статус подачи" value={status} onChange={(e) => setStatus(e.target.value as Status | "all")}>
          <option value="all">Любой статус</option>
          <option value="submitted">Подано</option>
          <option value="pending">Ещё не подано</option>
          <option value="forecast">По прогнозу</option>
        </select>
      </div>
      <ResultsBar shown={visible.length} total={rows.length} filtered={filtered} onReset={reset} />

      <div className="table-scroll">
        <table className="dash-table">
          <thead>
            <tr>
              <SortHeader label="Группа" sortKey="code" sort={sort} onSort={(k) => setSort((s) => nextSort(s, k))} />
              <SortHeader label="Куратор" sortKey="curator" sort={sort} onSort={(k) => setSort((s) => nextSort(s, k))} />
              <SortHeader label="Питающихся" sortKey="eaters" sort={sort} onSort={(k) => setSort((s) => nextSort(s, k))} />
              {dates.map((d) => (
                <SortHeader key={d} label={formatDueShort(d)} sortKey={`day:${d}`} sort={sort} onSort={(k) => setSort((s) => nextSort(s, k))} />
              ))}
              <SortHeader label="Подача" sortKey="status" sort={sort} onSort={(k) => setSort((s) => nextSort(s, k))} />
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.study_group_id} className="clickable-row" onClick={() => setOpenGroup(r)} title="Показать, кто питается">
                <td>{r.code}</td>
                <td>{r.curator_name ?? "нет куратора"}</td>
                <td>{r.eaters}</td>
                {dates.map((d) => {
                  const day = r.days.find((x) => x.date === d);
                  return (
                    <td key={d} className={day ? `meals-overview__cell--${day.source}` : undefined} title={day ? `${STATUS_TEXT_SOURCE[day.source]}` : undefined}>
                      {day ? day.count : "—"}
                    </td>
                  );
                })}
                <td>{STATUS_TEXT[r.status]}</td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={4 + dates.length}>{rows.length === 0 ? "На эту неделю данных нет." : "Под выбранные фильтры ничего не подошло."}</td>
              </tr>
            )}
          </tbody>
          {visible.length > 0 && (
            <tfoot>
              <tr className="meals-overview__totals">
                <td colSpan={2}>Итого</td>
                <td>{visible.reduce((sum, r) => sum + r.eaters, 0)}</td>
                {dates.map((d) => (
                  <td key={d}>{totals[d] ?? 0}</td>
                ))}
                <td />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      <p className="hint">Курсивом на жёлтом — число по прогнозу (куратор не подал), жирным — поправка куратора на день.</p>

      {openGroup && <GroupDialog row={openGroup} onClose={() => setOpenGroup(null)} />}
    </div>
  );
}

const STATUS_TEXT_SOURCE: Record<"submitted" | "edited" | "forecast", string> = {
  submitted: "подано куратором",
  edited: "поправка куратора на день",
  forecast: "прогноз",
};

function GroupDialog({ row, onClose }: { row: MealOverviewRow; onClose: () => void }) {
  useEscapeKey(onClose);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--wide" role="dialog" aria-modal="true" aria-label={`Питание группы ${row.code}`} onClick={(e) => e.stopPropagation()}>
        <h3>
          Группа {row.code} <span className="hint">· {row.department_name}</span>
        </h3>
        <GroupMealsPanel groupId={row.study_group_id} viewOnly />
        <div className="actions">
          <button onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}
