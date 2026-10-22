import { useMemo } from "react";
import type { DynamicsPoint } from "../../api/types";
import { formatDateRu } from "../../utils/date";
import { nextSort, sortRows } from "../../utils/tableView";
import type { SortState } from "../../utils/tableView";
import { useEntryState } from "../../hooks/useEntryState";
import ResultsBar from "./ResultsBar";
import SortHeader from "./SortHeader";
import PercentBar from "./PercentBar";
import LoadState from "./LoadState";
import { useDashboardRows } from "./useDashboardRows";

type DynKey = "date" | "in_list" | "present" | "percent";

/** «Динамика»: посещаемость по дням периода — график и таблица. */
export default function DynamicsTab({ dateFrom, dateTo, deptQuery, reloadKey }: {
  dateFrom: string;
  dateTo: string;
  deptQuery: string;
  reloadKey: number;
}) {
  const { rows: dynamicsPoints, error, loading } = useDashboardRows<DynamicsPoint>(
    `/dashboards/dynamics?date_from=${dateFrom}&date_to=${dateTo}${deptQuery}`, reloadKey,
  );
  const [dynOnlyData, setDynOnlyData] = useEntryState("dynOnlyData", false);
  const [dynBelow, setDynBelow] = useEntryState("dynBelow", "");
  const [dynSort, setDynSort] = useEntryState<SortState<DynKey> | null>("dynSort", null);

  const dynBelowNum = dynBelow.trim() === "" ? null : Number(dynBelow);
  const dynFiltered = dynOnlyData || dynBelowNum !== null;
  const visibleDynamics = useMemo(() => {
    let rows = dynamicsPoints;
    if (dynOnlyData) rows = rows.filter((p) => p.percent !== null);
    if (dynBelowNum !== null && !Number.isNaN(dynBelowNum)) rows = rows.filter((p) => p.percent !== null && p.percent < dynBelowNum);
    return sortRows(rows, dynSort, {
      date: (p) => p.date, in_list: (p) => p.in_list, present: (p) => p.present, percent: (p) => p.percent,
    });
  }, [dynamicsPoints, dynOnlyData, dynBelowNum, dynSort]);

  return (
    <>
      <LoadState error={error} loading={loading} />
      <>
        <DynamicsChart points={dynamicsPoints} />
        <div className="toolbar toolbar--filters">
          <label className="check-inline">
            <input type="checkbox" checked={dynOnlyData} onChange={(e) => setDynOnlyData(e.target.checked)} /> Только дни с данными
          </label>
          <input type="number" min={0} max={100} value={dynBelow} onChange={(e) => setDynBelow(e.target.value)} placeholder="Посещаемость ниже, %" aria-label="Посещаемость ниже, %" />
        </div>
        <ResultsBar shown={visibleDynamics.length} total={dynamicsPoints.length} filtered={dynFiltered} onReset={() => { setDynOnlyData(false); setDynBelow(""); }} />
        <div className="table-scroll"><table className="dash-table">
          <thead>
            <tr>
              <SortHeader label="Дата" sortKey="date" sort={dynSort} onSort={(k) => setDynSort((s) => nextSort(s, k))} />
              <SortHeader label="В списке" sortKey="in_list" sort={dynSort} onSort={(k) => setDynSort((s) => nextSort(s, k))} />
              <SortHeader label="Присутствовало" sortKey="present" sort={dynSort} onSort={(k) => setDynSort((s) => nextSort(s, k))} />
              <SortHeader label="%" sortKey="percent" sort={dynSort} onSort={(k) => setDynSort((s) => nextSort(s, k))} />
            </tr>
          </thead>
          <tbody>
            {visibleDynamics.map((p) => (
              <tr key={p.date}>
                <td>{formatDateRu(p.date)}</td>
                <td>{p.in_list ?? "—"}</td>
                <td>{p.present ?? "—"}</td>
                <td>
                  <PercentBar value={p.percent} />
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </>
    </>
  );
}

// "Динамика" была таблицей без наглядности — среднее и график по точкам
// (см. TODO.md 4). Своя лёгкая SVG-полоска вместо графической библиотеки.
function DynamicsChart({ points }: { points: DynamicsPoint[] }) {
  const withValue = points.filter((p): p is DynamicsPoint & { percent: number } => p.percent !== null && p.percent !== undefined);
  if (withValue.length === 0) return null;
  const average = withValue.reduce((sum, p) => sum + p.percent, 0) / withValue.length;
  const barWidth = 100 / points.length;
  return (
    <div className="dynamics-chart">
      <p>
        Среднее за период: <b>{average.toFixed(1)}%</b>
      </p>
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="dynamics-chart__svg">
        {points.map((p, i) => {
          if (p.percent === null || p.percent === undefined) return null;
          const height = (Math.min(p.percent, 100) / 100) * 40;
          const color = p.percent >= 95 ? "var(--ok)" : p.percent >= 85 ? "var(--warn)" : "var(--danger)";
          return (
            <rect
              key={p.date}
              x={i * barWidth}
              y={40 - height}
              width={Math.max(barWidth - 0.5, 0.5)}
              height={height}
              fill={color}
            >
              <title>
                {formatDateRu(p.date)}: {p.percent.toFixed(1)}%
              </title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}
