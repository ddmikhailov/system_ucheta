import { useMemo, useState } from "react";
import type { CuratorDisciplineRow } from "../../api/types";
import CuratorDaysModal from "../CuratorDaysModal";
import { filterByQuery } from "../../utils/searchMatch";
import { nextSort, sortRows } from "../../utils/tableView";
import type { SortState } from "../../utils/tableView";
import { useEntryState } from "../../hooks/useEntryState";
import ResultsBar from "./ResultsBar";
import SortHeader from "./SortHeader";
import LoadState from "./LoadState";
import { useDashboardRows } from "./useDashboardRows";

type DiscKey = "code" | "course" | "responsible" | "on_time" | "late" | "missed" | "total";

const NO_CURATOR = "нет куратора";

/** «Дисциплина кураторов»: вовремя ли сдавались дни за период; зав. отделением открывает разбор по дням. */
export default function DisciplineTab({ dateFrom, dateTo, deptQuery, reloadKey, isDeptHead }: {
  dateFrom: string;
  dateTo: string;
  deptQuery: string;
  reloadKey: number;
  isDeptHead: boolean;
}) {
  const { rows: disciplineRows, error, loading } = useDashboardRows<CuratorDisciplineRow>(
    `/dashboards/curator-discipline?date_from=${dateFrom}&date_to=${dateTo}${deptQuery}`, reloadKey,
  );
  const [discQuery, setDiscQuery] = useEntryState("discQuery", "");
  const [discCourse, setDiscCourse] = useEntryState<number | "all">("discCourse", "all");
  const [discOnlyMissed, setDiscOnlyMissed] = useEntryState("discOnlyMissed", false);
  const [discSort, setDiscSort] = useEntryState<SortState<DiscKey> | null>("discSort", null);
  const [openDisciplineGroupId, setOpenDisciplineGroupId] = useState<number | null>(null);

  const discCourses = useMemo(
    () => Array.from(new Set(disciplineRows.map((r) => r.course))).sort((a, b) => a - b),
    [disciplineRows],
  );
  const discFiltered = discQuery.trim() !== "" || discCourse !== "all" || discOnlyMissed;
  const visibleDiscipline = useMemo(() => {
    let rows = disciplineRows;
    if (discCourse !== "all") rows = rows.filter((r) => r.course === discCourse);
    if (discOnlyMissed) rows = rows.filter((r) => r.missed > 0);
    rows = filterByQuery(rows, discQuery, (r) => `${r.code} ${r.responsible_name ?? NO_CURATOR}`);
    return sortRows(rows, discSort, {
      code: (r) => r.code, course: (r) => r.course, responsible: (r) => r.responsible_name,
      on_time: (r) => r.on_time, late: (r) => r.late, missed: (r) => r.missed, total: (r) => r.total_study_days,
    });
  }, [disciplineRows, discCourse, discOnlyMissed, discQuery, discSort]);

  return (
    <>
      <LoadState error={error} loading={loading} />
      {isDeptHead && <p className="hint">Нажмите на строку, чтобы увидеть по дням, во сколько сдавался день и кем.</p>}
      <>
        <div className="toolbar toolbar--filters">
          <input type="search" value={discQuery} onChange={(e) => setDiscQuery(e.target.value)} placeholder="Группа или ответственный" aria-label="Поиск по группе или ответственному" />
          <select aria-label="Курс" value={discCourse} onChange={(e) => setDiscCourse(e.target.value === "all" ? "all" : Number(e.target.value))}>
            <option value="all">Все курсы</option>
            {discCourses.map((c) => (
              <option key={c} value={c}>Курс {c}</option>
            ))}
          </select>
          <label className="check-inline">
            <input type="checkbox" checked={discOnlyMissed} onChange={(e) => setDiscOnlyMissed(e.target.checked)} /> Только с несданными днями
          </label>
        </div>
        <ResultsBar shown={visibleDiscipline.length} total={disciplineRows.length} filtered={discFiltered} onReset={() => { setDiscQuery(""); setDiscCourse("all"); setDiscOnlyMissed(false); }} />
      </>
      <div className="table-scroll"><table className="dash-table">
        <thead>
          <tr>
            <SortHeader label="Группа" sortKey="code" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
            <SortHeader label="Курс" sortKey="course" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
            <SortHeader label="Ответственный" sortKey="responsible" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
            <SortHeader label="Вовремя" sortKey="on_time" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
            <SortHeader label="С опозданием" sortKey="late" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
            <SortHeader label="Не сдано" sortKey="missed" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
            <SortHeader label="Всего учебных дней" sortKey="total" sort={discSort} onSort={(k) => setDiscSort((s) => nextSort(s, k))} />
          </tr>
        </thead>
        <tbody>
          {visibleDiscipline.map((r) => (
            <tr
              key={r.study_group_id}
              className={`${r.missed > 0 ? "not-submitted-row" : ""}${isDeptHead ? " clickable-row" : ""}`}
              onClick={isDeptHead ? () => setOpenDisciplineGroupId(r.study_group_id) : undefined}
              title={isDeptHead ? "Показать по дням: во сколько сдавали" : undefined}
            >
              <td>{r.code}</td>
              <td>{r.course}</td>
              <td>{r.responsible_name ?? "нет куратора"}</td>
              <td>{r.on_time}</td>
              <td>{r.late}</td>
              <td>{r.missed}</td>
              <td>{r.total_study_days}</td>
            </tr>
          ))}
          {visibleDiscipline.length === 0 && (
            <tr>
              <td colSpan={7}>{disciplineRows.length === 0 ? "Нет данных за выбранный период." : "Под выбранные фильтры ничего не подошло."}</td>
            </tr>
          )}
        </tbody>
      </table></div>
      {openDisciplineGroupId !== null && (
        <CuratorDaysModal
          studyGroupId={openDisciplineGroupId}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onClose={() => setOpenDisciplineGroupId(null)}
        />
      )}
    </>
  );
}
