import { useMemo } from "react";
import type { StudyGroupAdmin } from "../../api/types";
import { filterByQuery } from "../../utils/searchMatch";
import { nextSort, sortRows } from "../../utils/tableView";
import type { SortState } from "../../utils/tableView";
import { useEntryState } from "../../hooks/useEntryState";
import ResultsBar from "./ResultsBar";
import SortHeader from "./SortHeader";

type VacantKey = "code" | "course";

/** «Вакантные группы»: активные группы без куратора — назначить куратора прямо отсюда. */
export default function VacantTab({ vacantGroups, onAssign }: { vacantGroups: StudyGroupAdmin[]; onAssign: (groupId: number) => void }) {
  const [vacantQuery, setVacantQuery] = useEntryState("vacantQuery", "");
  const [vacantCourse, setVacantCourse] = useEntryState<number | "all">("vacantCourse", "all");
  const [vacantSort, setVacantSort] = useEntryState<SortState<VacantKey> | null>("vacantSort", null);
  const vacantCourses = useMemo(() => Array.from(new Set(vacantGroups.map((g) => g.course))).sort((a, b) => a - b), [vacantGroups]);
  const vacantFiltered = vacantQuery.trim() !== "" || vacantCourse !== "all";
  const visibleVacant = useMemo(() => {
    let rows = vacantGroups;
    if (vacantCourse !== "all") rows = rows.filter((g) => g.course === vacantCourse);
    rows = filterByQuery(rows, vacantQuery, (g) => g.code);
    return sortRows(rows, vacantSort, { code: (g) => g.code, course: (g) => g.course });
  }, [vacantGroups, vacantCourse, vacantQuery, vacantSort]);

  return (
    <>
      <p className="hint">
        Пока куратор не назначен, отмечать посещаемость в группе некому: в витринах она будет значиться как
        «не сдано». Назначьте куратора или заместителя, чтобы группа заработала как обычно.
      </p>
      <div className="toolbar toolbar--filters">
        <input type="search" value={vacantQuery} onChange={(e) => setVacantQuery(e.target.value)} placeholder="Код группы" aria-label="Поиск по коду группы" />
        <select aria-label="Курс" value={vacantCourse} onChange={(e) => setVacantCourse(e.target.value === "all" ? "all" : Number(e.target.value))}>
          <option value="all">Все курсы</option>
          {vacantCourses.map((c) => (
            <option key={c} value={c}>Курс {c}</option>
          ))}
        </select>
      </div>
      <ResultsBar shown={visibleVacant.length} total={vacantGroups.length} filtered={vacantFiltered} onReset={() => { setVacantQuery(""); setVacantCourse("all"); }} />
      <div className="table-scroll"><table className="dash-table">
        <thead>
          <tr>
            <SortHeader label="Группа" sortKey="code" sort={vacantSort} onSort={(k) => setVacantSort((s) => nextSort(s, k))} />
            <SortHeader label="Курс" sortKey="course" sort={vacantSort} onSort={(k) => setVacantSort((s) => nextSort(s, k))} />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {visibleVacant.map((g) => (
            <tr key={g.id} className="not-submitted-row">
              <td>{g.code}</td>
              <td>{g.course}</td>
              <td>
                <button onClick={() => onAssign(g.id)}>Назначить куратора</button>
              </td>
            </tr>
          ))}
          {visibleVacant.length === 0 && (
            <tr>
              <td colSpan={3}>{vacantGroups.length === 0 ? "Вакантных групп нет — у каждой есть куратор." : "Под выбранные фильтры ничего не подошло."}</td>
            </tr>
          )}
        </tbody>
      </table></div>
    </>
  );
}
