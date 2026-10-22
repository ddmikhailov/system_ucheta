import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { RiskStudentRow } from "../../api/types";
import { formatPercent } from "../../utils/percent";
import { filterByQuery } from "../../utils/searchMatch";
import { nextSort, sortRows } from "../../utils/tableView";
import type { SortState } from "../../utils/tableView";
import { useEntryState } from "../../hooks/useEntryState";
import ResultsBar from "./ResultsBar";
import SortHeader from "./SortHeader";
import LoadState from "./LoadState";
import { useDashboardRows } from "./useDashboardRows";

type RiskKey = "name" | "group" | "percent" | "unexcused" | "absent";

/** «Группа риска» и «Восполнить пропуски» на выбранную дату. */
export default function RiskTab({ date, deptQuery, reloadKey }: { date: string; deptQuery: string; reloadKey: number }) {
  const { rows: riskRows, error, loading } = useDashboardRows<RiskStudentRow>(
    `/dashboards/risk-students?as_of_date=${date}${deptQuery}`, reloadKey,
  );
  const [riskQuery, setRiskQuery] = useEntryState("riskQuery", "");
  const [riskGroup, setRiskGroup] = useEntryState<number | "all">("riskGroup", "all");
  const [riskBelow, setRiskBelow] = useEntryState("riskBelow", "");
  // Группа риска и «Восполнить пропуски» приходят одним списком; по умолчанию — только группа риска.
  const [riskCategory, setRiskCategory] = useEntryState<RiskStudentRow["category"] | "all">("riskCategory", "risk");
  const [riskSort, setRiskSort] = useEntryState<SortState<RiskKey> | null>("riskSort", null);

  const riskBelowNum = riskBelow.trim() === "" ? null : Number(riskBelow);
  const riskFiltered = riskQuery.trim() !== "" || riskGroup !== "all" || riskBelowNum !== null;
  const riskGroups = useMemo(() => {
    const byId = new Map<number, string>();
    for (const r of riskRows) byId.set(r.study_group_id, r.group_code);
    return [...byId].sort((a, b) => a[1].localeCompare(b[1], "ru", { numeric: true }));
  }, [riskRows]);
  const riskInCategory = useMemo(
    () => (riskCategory === "all" ? riskRows : riskRows.filter((r) => r.category === riskCategory)),
    [riskRows, riskCategory]
  );
  const visibleRisk = useMemo(() => {
    let rows = riskInCategory;
    if (riskGroup !== "all") rows = rows.filter((r) => r.study_group_id === riskGroup);
    if (riskBelowNum !== null && !Number.isNaN(riskBelowNum)) rows = rows.filter((r) => r.attendance_percent < riskBelowNum);
    rows = filterByQuery(rows, riskQuery, (r) => `${r.full_name} ${r.group_code}`);
    return sortRows(rows, riskSort, {
      name: (r) => r.full_name, group: (r) => r.group_code, percent: (r) => r.attendance_percent,
      unexcused: (r) => r.unexcused_percent, absent: (r) => r.absent,
    });
  }, [riskInCategory, riskGroup, riskBelowNum, riskQuery, riskSort]);


  return (
    <>
      <LoadState error={error} loading={loading} />
      <>
        <div className="toolbar toolbar--filters">
          <select aria-label="Список" value={riskCategory} onChange={(e) => setRiskCategory(e.target.value as RiskStudentRow["category"] | "all")}>
            <option value="risk">Группа риска ({riskRows.filter((r) => r.category === "risk").length})</option>
            <option value="compensation">Восполнить пропуски ({riskRows.filter((r) => r.category === "compensation").length})</option>
            <option value="all">Все ({riskRows.length})</option>
          </select>
          <input type="search" value={riskQuery} onChange={(e) => setRiskQuery(e.target.value)} placeholder="Студент или группа" aria-label="Поиск по студенту или группе" />
          <select aria-label="Группа" value={riskGroup} onChange={(e) => setRiskGroup(e.target.value === "all" ? "all" : Number(e.target.value))}>
            <option value="all">Все группы</option>
            {riskGroups.map(([id, code]) => (
              <option key={id} value={id}>{code}</option>
            ))}
          </select>
          <input type="number" min={0} max={100} value={riskBelow} onChange={(e) => setRiskBelow(e.target.value)} placeholder="Посещаемость ниже, %" aria-label="Посещаемость ниже, %" />
        </div>
        <p className="hint">
          Группа риска — пропусков без уважительной причины больше 40 % с начала семестра: нужна индивидуальная работа.
          «Восполнить пропуски» — пропущен учебный процесс по уважительной причине (практика и ИУП не в счёт): куратор
          закрывает, когда студент догнал программу.
        </p>
        <ResultsBar shown={visibleRisk.length} total={riskInCategory.length} filtered={riskFiltered} onReset={() => { setRiskQuery(""); setRiskGroup("all"); setRiskBelow(""); }} />
      </>
      <div className="table-scroll"><table className="dash-table">
        <thead>
          <tr>
            <SortHeader label="Студент" sortKey="name" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
            <SortHeader label="Группа" sortKey="group" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
            <th>Статус</th>
            <SortHeader label="Посещаемость с начала семестра" sortKey="percent" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
            <SortHeader label="Без уважительной причины" sortKey="unexcused" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
            <SortHeader label="Пропущено дней" sortKey="absent" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
          </tr>
        </thead>
        <tbody>
          {visibleRisk.map((r) => (
            <tr key={r.student_id} className={r.category === "risk" ? "risk-row" : ""}>
              <td>
                <Link to={`/students/${r.student_id}`} className="link-btn">
                  {r.full_name}
                </Link>
              </td>
              <td>{r.group_code}</td>
              <td>
                {r.category === "risk" ? (
                  <span className="risk-badge">группа риска</span>
                ) : (
                  <span className="compensate-badge">восполнить пропуски</span>
                )}
              </td>
              <td>{formatPercent(r.attendance_percent)}</td>
              <td>{formatPercent(r.unexcused_percent)}</td>
              <td>
                {r.absent} из {r.days}
              </td>
            </tr>
          ))}
          {visibleRisk.length === 0 && (
            <tr>
              <td colSpan={6}>{riskInCategory.length === 0 ? "Нет таких студентов на выбранную дату." : "Под выбранные фильтры ничего не подошло."}</td>
            </tr>
          )}
        </tbody>
      </table></div>
    </>
  );
}
