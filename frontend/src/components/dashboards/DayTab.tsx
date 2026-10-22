import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type { DayOverviewRow } from "../../api/types";
import { filterByQuery } from "../../utils/searchMatch";
import { nextSort, sortRows } from "../../utils/tableView";
import type { SortState } from "../../utils/tableView";
import { useEntryState } from "../../hooks/useEntryState";
import ResultsBar from "./ResultsBar";
import SortHeader from "./SortHeader";
import LoadState from "./LoadState";
import { useDashboardRows } from "./useDashboardRows";
import PercentBar from "./PercentBar";

type DayKey = "code" | "course" | "responsible" | "in_list" | "present" | "late" | "excused" | "unexcused" | "percent" | "submitted";
type DayStatus = "all" | "missing" | "on_time" | "late";

const NO_CURATOR = "нет куратора";

/** «День по колледжу/отделению»: сдача дня и посещаемость по группам на выбранную дату. */
export default function DayTab({ date, deptQuery, reloadKey, isStaff }: {
  date: string;
  deptQuery: string;
  reloadKey: number;
  isStaff: boolean;
}) {
  const navigate = useNavigate();
  const { rows: dayRows, error, loading } = useDashboardRows<DayOverviewRow>(`/dashboards/day?date=${date}${deptQuery}`, reloadKey);
  const [courseFilter, setCourseFilter] = useEntryState<number | "all">("courseFilter", "all");
  // Фильтры и сортировки таблиц: считаются на странице по уже загруженным строкам.
  const [dayQuery, setDayQuery] = useEntryState("dayQuery", "");
  const [dayStatus, setDayStatus] = useEntryState<DayStatus>("dayStatus", "all");
  const [dayOnlyAbsent, setDayOnlyAbsent] = useEntryState("dayOnlyAbsent", false);
  const [daySort, setDaySort] = useEntryState<SortState<DayKey> | null>("daySort", null);

  const courses = useMemo(
    () => Array.from(new Set(dayRows.map((r) => r.course))).sort((a, b) => a - b),
    [dayRows],
  );
  const dayFiltered = courseFilter !== "all" || dayQuery.trim() !== "" || dayStatus !== "all" || dayOnlyAbsent;
  const visibleDayRows = useMemo(() => {
    let rows = dayRows;
    if (courseFilter !== "all") rows = rows.filter((r) => r.course === courseFilter);
    if (dayStatus === "missing") rows = rows.filter((r) => !r.is_submitted);
    else if (dayStatus === "on_time") rows = rows.filter((r) => r.is_submitted && r.is_on_time);
    else if (dayStatus === "late") rows = rows.filter((r) => r.is_submitted && !r.is_on_time);
    if (dayOnlyAbsent) rows = rows.filter((r) => (r.absent_unexcused ?? 0) > 0);
    rows = filterByQuery(rows, dayQuery, (r) => `${r.code} ${r.responsible_name ?? NO_CURATOR}`);
    return sortRows(rows, daySort, {
      code: (r) => r.code, course: (r) => r.course, responsible: (r) => r.responsible_name,
      in_list: (r) => r.in_list, present: (r) => r.present, late: (r) => r.late,
      excused: (r) => r.absent_excused, unexcused: (r) => r.absent_unexcused, percent: (r) => r.percent,
      submitted: (r) => (!r.is_submitted ? 0 : r.is_on_time ? 2 : 1),
    });
  }, [dayRows, courseFilter, dayQuery, dayStatus, dayOnlyAbsent, daySort]);
  function resetDayFilters() {
    setCourseFilter("all");
    setDayQuery("");
    setDayStatus("all");
    setDayOnlyAbsent(false);
  }

  return (
    <>
      <LoadState error={error} loading={loading} />
      <>
        <div className="toolbar toolbar--filters">
          <input type="search" value={dayQuery} onChange={(e) => setDayQuery(e.target.value)} placeholder="Группа или ответственный" aria-label="Поиск по группе или ответственному" />
          <select aria-label="Курс" value={courseFilter} onChange={(e) => setCourseFilter(e.target.value === "all" ? "all" : Number(e.target.value))}>
            <option value="all">Все курсы</option>
            {courses.map((c) => (
              <option key={c} value={c}>
                Курс {c}
              </option>
            ))}
          </select>
          <select aria-label="Статус сдачи" value={dayStatus} onChange={(e) => setDayStatus(e.target.value as DayStatus)}>
            <option value="all">Любой статус сдачи</option>
            <option value="missing">Не сдано</option>
            <option value="on_time">Сдано вовремя</option>
            <option value="late">Сдано задним числом</option>
          </select>
          <label className="check-inline">
            <input type="checkbox" checked={dayOnlyAbsent} onChange={(e) => setDayOnlyAbsent(e.target.checked)} /> Только с пропусками без причины
          </label>
        </div>
        <ResultsBar shown={visibleDayRows.length} total={dayRows.length} filtered={dayFiltered} onReset={resetDayFilters} />
      </>
      <div className="table-scroll"><table className="dash-table">
        <thead>
          <tr>
            <SortHeader label="Группа" sortKey="code" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Курс" sortKey="course" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Ответственный" sortKey="responsible" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="В списке" sortKey="in_list" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Пришло" sortKey="present" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Опоздало" sortKey="late" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Отс. уваж." sortKey="excused" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Отс. неуваж." sortKey="unexcused" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="%" sortKey="percent" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
            <SortHeader label="Сдано" sortKey="submitted" sort={daySort} onSort={(k) => setDaySort((s) => nextSort(s, k))} />
          </tr>
        </thead>
        <tbody>
          {visibleDayRows.map((r) => (
            <tr
              key={r.study_group_id}
              className={!r.is_submitted ? "not-submitted-row clickable-row" : "clickable-row"}
              onClick={() =>
                navigate(isStaff ? `/students?group=${r.study_group_id}` : `/admin?tab=journal&group=${r.study_group_id}&date=${date}`)
              }
              title={isStaff ? "Показать студентов группы" : "Открыть журнал группы на эту дату"}
            >
              <td>{r.code}</td>
              <td>{r.course}</td>
              <td>{r.responsible_name ?? "нет куратора"}</td>
              <td>{r.in_list ?? "—"}</td>
              <td>{r.present ?? "—"}</td>
              <td>{r.late ?? "—"}</td>
              <td>{r.absent_excused ?? "—"}</td>
              <td>{r.absent_unexcused ?? "—"}</td>
              <td>
                <PercentBar value={r.percent} />
              </td>
              <td>{r.is_submitted ? (r.is_on_time ? "вовремя" : "задним числом") : "не сдано"}</td>
            </tr>
          ))}
          {visibleDayRows.length === 0 && (
            <tr>
              <td colSpan={10}>{dayRows.length === 0 ? "Нет данных на выбранную дату." : "Под выбранные фильтры ничего не подошло."}</td>
            </tr>
          )}
        </tbody>
      </table></div>
    </>
  );
}
