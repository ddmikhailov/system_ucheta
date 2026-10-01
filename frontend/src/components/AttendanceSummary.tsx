import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AttendanceSummary, SummaryCode, SummaryLine } from "../api/types";

type View = "daily" | "period" | "groups";

const VIEW_LABELS: Record<View, string> = {
  daily: "По дням",
  period: "За период",
  groups: "По группам и дням",
};

const FIRST_PERIOD_SLICE = "К 1 паре";

function formatDateRu(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function percentText(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}

function CodeHeaders({ codes }: { codes: SummaryCode[] }) {
  return (
    <>
      {codes.map((c) => (
        <th key={c.code} title={c.name}>
          {c.code.toUpperCase()}
        </th>
      ))}
    </>
  );
}

/** Свод посещаемости «всего / к 1 паре» — те же числа, что в листах свода в
 * выгрузке Excel: по дням, за период и по группам. По каждой строке видно,
 * сколько студентов прибыло и сколько отметок по каждому коду. */
export default function AttendanceSummaryView({
  dateFrom,
  dateTo,
  departmentId,
}: {
  dateFrom: string;
  dateTo: string;
  departmentId: number | "all";
}) {
  const [view, setView] = useState<View>("daily");
  const [result, setResult] = useState<{ key: string; data: AttendanceSummary | null; error: string | null } | null>(
    null,
  );
  const [groupFilter, setGroupFilter] = useState("");

  const rangeInvalid = dateFrom > dateTo;
  const requestKey = `${dateFrom}|${dateTo}|${departmentId}|${view}`;

  useEffect(() => {
    if (rangeInvalid) return;
    let cancelled = false;
    const dept = departmentId !== "all" ? `&department_id=${departmentId}` : "";
    const detail = view === "groups" ? "&include_group_days=true" : "";
    api
      .get<AttendanceSummary>(`/dashboards/summary?date_from=${dateFrom}&date_to=${dateTo}${dept}${detail}`)
      .then((data) => {
        if (!cancelled) setResult({ key: requestKey, data, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({ key: requestKey, data: null, error: err instanceof ApiError ? err.message : "Ошибка загрузки" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, departmentId, view, rangeInvalid, requestKey]);

  // Ответ относится к текущим параметрам только если ключ совпал — иначе
  // идёт загрузка (старый ответ не показываем под новыми датами).
  const current = result?.key === requestKey ? result : null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;
  const loading = !rangeInvalid && current === null;

  const groupRows = useMemo(() => {
    const query = groupFilter.trim().toLowerCase();
    const rows = data?.group_days ?? [];
    return query ? rows.filter((r) => r.group_code.toLowerCase().includes(query)) : rows;
  }, [data, groupFilter]);

  const codes = data?.codes ?? [];

  function lineRow(line: SummaryLine, withDate: boolean) {
    const isFirst = line.slice_name === FIRST_PERIOD_SLICE;
    return (
      <tr
        key={`${line.date ?? "period"}-${line.department}-${line.slice_name}`}
        className={isFirst ? "summary-first-row" : "summary-all-row"}
      >
        {withDate && <td data-label="Дата">{line.date ? formatDateRu(line.date) : ""}</td>}
        <td data-label="Отделение">{line.department}</td>
        <td data-label="Срез">
          <b>{line.slice_name}</b>
        </td>
        <td data-label="Групп сдали">
          {line.groups_submitted}
          {withDate ? ` из ${line.groups}` : ""}
        </td>
        <td data-label="Численность">{line.headcount}</td>
        <td data-label="Учтено">{line.counted}</td>
        <td data-label="Прибыли">{line.present}</td>
        <td data-label="Отсутствуют">{line.absent}</td>
        <td data-label="%">{percentText(line.percent)}</td>
        {codes.map((c) => (
          <td key={c.code} data-label={c.name}>
            {line.by_code[c.code] ?? 0}
          </td>
        ))}
      </tr>
    );
  }

  return (
    <div>
      <div className="toolbar">
        {(Object.keys(VIEW_LABELS) as View[]).map((v) => (
          <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
            {VIEW_LABELS[v]}
          </button>
        ))}
        {view === "groups" && (
          <input placeholder="Фильтр по коду группы" value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)} />
        )}
      </div>

      <p className="hint">
        «Учтено» — студенты тех групп, что сдали день; несданные группы в «Прибыли» не попадают. «К 1 паре» — группы,
        у которых куратор указал первую пару равной 1 (дни без указанной пары в этот срез не входят).
        {view === "period" && " За период числа — в студенто-днях."}
      </p>

      {rangeInvalid && <div className="error-text">Дата начала позже даты окончания</div>}
      {error && !rangeInvalid && <div className="error-text">{error}</div>}
      {loading && <p className="hint">Загрузка…</p>}

      {data && !rangeInvalid && view === "daily" && (
        <div className="table-scroll">
          <table className="dash-table summary-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Отделение</th>
                <th>Срез</th>
                <th>Групп сдали</th>
                <th>Численность</th>
                <th>Учтено</th>
                <th>Прибыли</th>
                <th>Отсутствуют</th>
                <th>%</th>
                <CodeHeaders codes={codes} />
              </tr>
            </thead>
            <tbody>
              {data.daily.map((line) => lineRow(line, true))}
              {data.daily.length === 0 && (
                <tr>
                  <td colSpan={9 + codes.length}>За выбранный период нет учебных дней.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {data && !rangeInvalid && view === "period" && (
        <div className="table-scroll">
          <table className="dash-table summary-table">
            <thead>
              <tr>
                <th>Отделение</th>
                <th>Срез</th>
                <th>Групп-дней сдано</th>
                <th>В списках</th>
                <th>Учтено</th>
                <th>Прибыли</th>
                <th>Отсутствуют</th>
                <th>%</th>
                <CodeHeaders codes={codes} />
              </tr>
            </thead>
            <tbody>
              {data.period.map((line) => lineRow(line, false))}
              {data.period.length === 0 && (
                <tr>
                  <td colSpan={8 + codes.length}>За выбранный период нет учебных дней.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {data && !rangeInvalid && view === "groups" && (
        <div className="table-scroll">
          <table className="dash-table summary-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Группа</th>
                <th>Курс</th>
                <th>Численность</th>
                <th>Сдан</th>
                <th>Прибыли</th>
                <th>Отсутствуют</th>
                <th>%</th>
                <th>К какой паре</th>
                <CodeHeaders codes={codes} />
              </tr>
            </thead>
            <tbody>
              {groupRows.map((r) => (
                <tr key={`${r.date}-${r.group_id}`} className={r.is_submitted ? "" : "not-submitted-row"}>
                  <td data-label="Дата">{formatDateRu(r.date)}</td>
                  <td data-label="Группа">{r.group_code}</td>
                  <td data-label="Курс">{r.course}</td>
                  <td data-label="Численность">{r.headcount}</td>
                  <td data-label="Сдан">{r.is_submitted ? "да" : "нет"}</td>
                  <td data-label="Прибыли">{r.present ?? "—"}</td>
                  <td data-label="Отсутствуют">{r.absent ?? "—"}</td>
                  <td data-label="%">{percentText(r.percent)}</td>
                  <td data-label="К какой паре">
                    {r.is_submitted ? (r.first_period ?? "не указана") : "—"}
                  </td>
                  {codes.map((c) => (
                    <td key={c.code} data-label={c.name}>
                      {r.is_submitted ? (r.by_code[c.code] ?? 0) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
              {groupRows.length === 0 && (
                <tr>
                  <td colSpan={9 + codes.length}>Нет данных за выбранный период.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
