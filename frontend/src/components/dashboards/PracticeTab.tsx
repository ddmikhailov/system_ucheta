import { useMemo } from "react";
import type { CurrentPracticeRow } from "../../api/types";
import { formatDateRu } from "../../utils/date";
import { useEntryState } from "../../hooks/useEntryState";
import { PRACTICE_STATE_LABEL } from "../practice";
import LoadState from "./LoadState";
import { useDashboardRows } from "./useDashboardRows";

/** «Практика»: какие группы сейчас на практике, какие скоро уйдут и по каким нет характеристики с места практики. */
export default function PracticeTab({ deptQuery, reloadKey }: { deptQuery: string; reloadKey: number }) {
  const { rows, error, loading } = useDashboardRows<CurrentPracticeRow>(`/practice/current${deptQuery ? `?${deptQuery.replace(/^&/, "")}` : ""}`, reloadKey);
  const [onlyNoReview, setOnlyNoReview] = useEntryState("practiceNoReview", false);
  const visible = useMemo(() => (onlyNoReview ? rows.filter((r) => r.state === "no_review") : rows), [rows, onlyNoReview]);
  const noReview = rows.filter((r) => r.state === "no_review").length;

  return (
    <>
      <LoadState error={error} loading={loading} />
      <div className="toolbar toolbar--filters">
        <label className="check-inline">
          <input type="checkbox" checked={onlyNoReview} onChange={(e) => setOnlyNoReview(e.target.checked)} /> Только без характеристики
          {noReview > 0 ? ` (${noReview})` : ""}
        </label>
      </div>
      {!loading && visible.length === 0 && <p className="hint">Сейчас нет групп на практике и практик, о которых нужно помнить.</p>}
      {visible.length > 0 && (
        <div className="table-scroll">
          <table className="dash-table roster-table">
            <thead>
              <tr>
                <th>Группа</th>
                <th>Период</th>
                <th>База</th>
                <th>Руководители</th>
                <th>Состояние</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  <td data-label="Группа">
                    {r.group_code}
                    <div className="hint">{r.course} курс · {r.department}</div>
                  </td>
                  <td data-label="Период">
                    {formatDateRu(r.date_from)} — {formatDateRu(r.date_to)}
                    <div className="hint">{r.kind_name}</div>
                  </td>
                  <td data-label="База">{r.base ?? "—"}</td>
                  <td data-label="Руководители">
                    {r.college_supervisor && <div>Колледж: {r.college_supervisor}</div>}
                    {r.base_supervisor && <div>База: {r.base_supervisor}</div>}
                    {r.phone && <div className="hint">{r.phone}</div>}
                    {!r.college_supervisor && !r.base_supervisor && !r.phone && "—"}
                  </td>
                  <td data-label="Состояние">
                    <span className={r.state === "no_review" ? "risk-badge" : "compensate-badge"}>{PRACTICE_STATE_LABEL[r.state]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
