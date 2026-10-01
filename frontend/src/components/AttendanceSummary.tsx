import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  AttendanceSummary,
  DepartmentAdmin,
  StudyGroupAdmin,
  SummaryCode,
  SummaryGroupDay,
  SummaryLine,
} from "../api/types";
import { toIso, todayIso } from "../utils/date";
import { daysAgoIso, defaultSummaryFilters } from "../utils/summaryFilters";
import type { SliceMode, SummaryFilters } from "../utils/summaryFilters";

type View = "daily" | "period" | "groups";

const VIEW_LABELS: Record<View, string> = {
  daily: "По дням",
  period: "За период",
  groups: "По группам и дням",
};

const ALL_SLICE = "Всего";
const PAIR_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8];
const COURSES = [1, 2, 3, 4];

function formatDateRu(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function percentText(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}

// ---- быстрые периоды ----

function monthStartIso(offset: number): string {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth() + offset, 1));
}

function monthEndIso(offset: number): string {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth() + offset + 1, 0));
}

const PRESETS: { label: string; range: () => [string, string] }[] = [
  { label: "Сегодня", range: () => [todayIso(), todayIso()] },
  { label: "Вчера", range: () => [daysAgoIso(1), daysAgoIso(1)] },
  { label: "7 дней", range: () => [daysAgoIso(6), todayIso()] },
  { label: "Этот месяц", range: () => [monthStartIso(0), todayIso()] },
  { label: "Прошлый месяц", range: () => [monthStartIso(-1), monthEndIso(-1)] },
];

// ---- сортировка ----

interface Sort {
  key: string;
  dir: 1 | -1;
}

type Accessor<T> = Record<string, (row: T) => string | number | null>;

function sortRows<T>(rows: T[], sort: Sort | null, accessors: Accessor<T>): T[] {
  const get = sort ? accessors[sort.key] : undefined;
  if (!sort || !get) return rows;
  return [...rows].sort((a, b) => {
    const va = get(a);
    const vb = get(b);
    if (va === null && vb === null) return 0;
    if (va === null) return 1; // пустые значения всегда внизу
    if (vb === null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * sort.dir;
    return String(va).localeCompare(String(vb), "ru") * sort.dir;
  });
}

const codeKey = (code: string) => `code:${code}`;

function lineAccessors(codes: SummaryCode[]): Accessor<SummaryLine> {
  const acc: Accessor<SummaryLine> = {
    date: (r) => r.date,
    department: (r) => r.department,
    slice: (r) => r.slice_name,
    groups_submitted: (r) => r.groups_submitted,
    headcount: (r) => r.headcount,
    counted: (r) => r.counted,
    present: (r) => r.present,
    absent: (r) => r.absent,
    percent: (r) => r.percent,
  };
  for (const c of codes) acc[codeKey(c.code)] = (r) => r.by_code[c.code] ?? 0;
  return acc;
}

function groupAccessors(codes: SummaryCode[]): Accessor<SummaryGroupDay> {
  const acc: Accessor<SummaryGroupDay> = {
    date: (r) => r.date,
    group: (r) => r.group_code,
    course: (r) => r.course,
    headcount: (r) => r.headcount,
    submitted: (r) => (r.is_submitted ? 1 : 0),
    present: (r) => r.present,
    absent: (r) => r.absent,
    percent: (r) => r.percent,
    pair: (r) => r.first_period,
  };
  for (const c of codes) acc[codeKey(c.code)] = (r) => (r.is_submitted ? (r.by_code[c.code] ?? 0) : null);
  return acc;
}

// ---- отбор строк на клиенте ----

interface RowFilter {
  slice: SliceMode;
  hideEmpty: boolean;
  onlyProblems: boolean;
  threshold: number;
}

function keepLine(line: SummaryLine, daily: boolean, f: RowFilter): boolean {
  if (f.slice === "all" && line.slice_name !== ALL_SLICE) return false;
  if (f.slice === "pair" && line.slice_name === ALL_SLICE) return false;
  if (f.onlyProblems) {
    const low = line.percent !== null && line.percent < f.threshold;
    const unsubmitted = daily && line.groups_submitted < line.groups;
    return low || unsubmitted;
  }
  return !(f.hideEmpty && line.counted === 0);
}

function keepGroupDay(row: SummaryGroupDay, query: string, f: RowFilter): boolean {
  if (query && !row.group_code.toLowerCase().includes(query)) return false;
  if (f.onlyProblems) return !row.is_submitted || (row.percent !== null && row.percent < f.threshold);
  return !(f.hideEmpty && !row.is_submitted);
}

function SortTh({
  label,
  sortKey,
  sort,
  onSort,
  title,
}: {
  label: string;
  sortKey: string;
  sort: Sort | null;
  onSort: (key: string) => void;
  title?: string;
}) {
  const active = sort?.key === sortKey;
  return (
    <th
      className="sortable-th"
      title={title ?? "Нажмите, чтобы отсортировать"}
      aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
      onClick={() => onSort(sortKey)}
    >
      {label}
      {active ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
    </th>
  );
}

/** Свод посещаемости «всего / к N паре» — те же числа, что в листах свода в
 * выгрузке Excel: по дням, за период и по группам. Сверху панель фильтров:
 * период, отделение, курс, группа, пара, срез, столбцы кодов, «только
 * проблемные» и сброс. Период, отделение, курс, группа и пара отбираются на
 * сервере, остальное — сразу в браузере. */
export default function AttendanceSummaryView({
  filters,
  onChange,
  canFilterDepartment,
  departments,
  groups,
}: {
  filters: SummaryFilters;
  onChange: (next: SummaryFilters) => void;
  canFilterDepartment: boolean;
  departments: DepartmentAdmin[];
  groups: StudyGroupAdmin[];
}) {
  const [view, setView] = useState<View>("daily");
  const [sort, setSort] = useState<Sort | null>(null);
  const [groupQuery, setGroupQuery] = useState("");
  const [result, setResult] = useState<{ key: string; data: AttendanceSummary | null; error: string | null } | null>(
    null,
  );

  const { dateFrom, dateTo, departmentId, course, groupId, pair } = filters;
  const rangeInvalid = dateFrom > dateTo;
  const requestKey = `${dateFrom}|${dateTo}|${departmentId}|${course}|${groupId}|${pair}|${view}`;

  useEffect(() => {
    if (rangeInvalid) return;
    let cancelled = false;
    const params = [`date_from=${dateFrom}`, `date_to=${dateTo}`, `pair=${pair}`];
    if (departmentId !== "all") params.push(`department_id=${departmentId}`);
    if (course !== "all") params.push(`course=${course}`);
    if (groupId !== "all") params.push(`study_group_id=${groupId}`);
    if (view === "groups") params.push("include_group_days=true");
    api
      .get<AttendanceSummary>(`/dashboards/summary?${params.join("&")}`)
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
  }, [dateFrom, dateTo, departmentId, course, groupId, pair, view, rangeInvalid, requestKey]);

  // Ответ относится к текущим параметрам только если ключ совпал — иначе
  // идёт загрузка (старый ответ не показываем под новыми фильтрами).
  const current = result?.key === requestKey ? result : null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;
  const loading = !rangeInvalid && current === null;

  const allCodes = useMemo(() => data?.codes ?? [], [data]);
  const visibleCodes = allCodes.filter((c) => !filters.hiddenCodes.includes(c.code));

  const groupOptions = useMemo(
    () =>
      groups.filter(
        (g) =>
          g.is_active &&
          (course === "all" || g.course === course) &&
          (departmentId === "all" || g.department_id === departmentId),
      ),
    [groups, course, departmentId],
  );

  const { slice, onlyProblems, threshold } = filters;
  const hideEmpty = filters.hideEmpty && !onlyProblems;

  const dailyLines = useMemo(() => {
    const rowFilter = { slice, hideEmpty, onlyProblems, threshold };
    return sortRows(
      (data?.daily ?? []).filter((l) => keepLine(l, true, rowFilter)),
      sort,
      lineAccessors(allCodes),
    );
  }, [data, allCodes, sort, slice, hideEmpty, onlyProblems, threshold]);

  const periodLines = useMemo(() => {
    const rowFilter = { slice, hideEmpty, onlyProblems, threshold };
    return sortRows(
      (data?.period ?? []).filter((l) => keepLine(l, false, rowFilter)),
      sort,
      lineAccessors(allCodes),
    );
  }, [data, allCodes, sort, slice, hideEmpty, onlyProblems, threshold]);

  const groupRows = useMemo(() => {
    const rowFilter = { slice, hideEmpty, onlyProblems, threshold };
    const query = groupQuery.trim().toLowerCase();
    return sortRows(
      (data?.group_days ?? []).filter((r) => keepGroupDay(r, query, rowFilter)),
      sort,
      groupAccessors(allCodes),
    );
  }, [data, allCodes, sort, groupQuery, slice, hideEmpty, onlyProblems, threshold]);

  function update(patch: Partial<SummaryFilters>) {
    onChange({ ...filters, ...patch });
  }

  // При смене отделения/курса выбранная группа могла выпасть из списка.
  function updateScope(patch: Partial<SummaryFilters>) {
    const next = { ...filters, ...patch };
    const stillThere = groups.some(
      (g) =>
        g.id === next.groupId &&
        (next.course === "all" || g.course === next.course) &&
        (next.departmentId === "all" || g.department_id === next.departmentId),
    );
    onChange({ ...next, groupId: stillThere ? next.groupId : "all" });
  }

  function changeView(next: View) {
    setView(next);
    setSort(null);
  }

  function toggleSort(key: string) {
    setSort((s) => (s?.key === key ? (s.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 }));
  }

  function toggleCode(code: string) {
    const hidden = filters.hiddenCodes.includes(code)
      ? filters.hiddenCodes.filter((c) => c !== code)
      : [...filters.hiddenCodes, code];
    update({ hiddenCodes: hidden });
  }

  function absenceOnly() {
    update({ hiddenCodes: allCodes.filter((c) => c.counts_as_present).map((c) => c.code) });
  }

  const pairLabel = `К ${pair} паре`;
  const isDefault =
    JSON.stringify(filters) === JSON.stringify(defaultSummaryFilters()) && groupQuery === "" && sort === null;

  function lineRow(line: SummaryLine, withDate: boolean) {
    const isPairRow = line.slice_name !== ALL_SLICE;
    return (
      <tr
        key={`${line.date ?? "period"}-${line.department}-${line.slice_name}`}
        className={isPairRow ? "summary-first-row" : "summary-all-row"}
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
        {visibleCodes.map((c) => (
          <td key={c.code} data-label={c.name}>
            {line.by_code[c.code] ?? 0}
          </td>
        ))}
      </tr>
    );
  }

  function codeHeaders() {
    return visibleCodes.map((c) => (
      <SortTh
        key={c.code}
        label={c.code.toUpperCase()}
        sortKey={codeKey(c.code)}
        sort={sort}
        onSort={toggleSort}
        title={`${c.name} — нажмите, чтобы отсортировать`}
      />
    ));
  }

  return (
    <div>
      <div className="filter-bar">
        <div className="filter-bar__row">
          {PRESETS.map((p) => {
            const [from, to] = p.range();
            const active = dateFrom === from && dateTo === to;
            return (
              <button
                key={p.label}
                className={`chip${active ? " active" : ""}`}
                onClick={() => update({ dateFrom: from, dateTo: to })}
              >
                {p.label}
              </button>
            );
          })}
          <input type="date" value={dateFrom} onChange={(e) => update({ dateFrom: e.target.value })} />
          <span>—</span>
          <input type="date" value={dateTo} onChange={(e) => update({ dateTo: e.target.value })} />
        </div>

        <div className="filter-bar__row">
          {canFilterDepartment && (
            <select
              value={departmentId}
              onChange={(e) => updateScope({ departmentId: e.target.value === "all" ? "all" : Number(e.target.value) })}
              title="Отделение"
            >
              <option value="all">Все отделения</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
          <select
            value={course}
            onChange={(e) => updateScope({ course: e.target.value === "all" ? "all" : Number(e.target.value) })}
            title="Курс"
          >
            <option value="all">Все курсы</option>
            {COURSES.map((c) => (
              <option key={c} value={c}>
                {c} курс
              </option>
            ))}
          </select>
          <select
            value={groupId}
            onChange={(e) => update({ groupId: e.target.value === "all" ? "all" : Number(e.target.value) })}
            title="Группа"
          >
            <option value="all">Все группы</option>
            {groupOptions.map((g) => (
              <option key={g.id} value={g.id}>
                {g.code}
              </option>
            ))}
          </select>
          <select value={slice} onChange={(e) => update({ slice: e.target.value as SliceMode })} title="Срез">
            <option value="both">Всего и «{pairLabel}»</option>
            <option value="all">Только «Всего»</option>
            <option value="pair">Только «{pairLabel}»</option>
          </select>
          <select value={pair} onChange={(e) => update({ pair: Number(e.target.value) })} title="Пара для среза «К N паре»">
            {PAIR_OPTIONS.map((n) => (
              <option key={n} value={n}>
                К {n} паре
              </option>
            ))}
          </select>
        </div>

        <div className="filter-bar__row">
          <details className="filter-dropdown">
            <summary>
              Столбцы кодов ({visibleCodes.length}/{allCodes.length})
            </summary>
            <div className="filter-dropdown__panel">
              <div className="filter-dropdown__actions">
                <button className="link-btn" onClick={() => update({ hiddenCodes: [] })}>
                  Все
                </button>
                <button className="link-btn" onClick={absenceOnly}>
                  Только пропуски
                </button>
              </div>
              {allCodes.map((c) => (
                <label key={c.code}>
                  <input
                    type="checkbox"
                    checked={!filters.hiddenCodes.includes(c.code)}
                    onChange={() => toggleCode(c.code)}
                  />{" "}
                  <b>{c.code.toUpperCase()}</b> — {c.name}
                </label>
              ))}
            </div>
          </details>

          <label className="filter-check">
            <input type="checkbox" checked={onlyProblems} onChange={(e) => update({ onlyProblems: e.target.checked })} />{" "}
            Только проблемные: ниже
            <input
              type="number"
              min={1}
              max={100}
              value={threshold}
              onChange={(e) => update({ threshold: Math.min(100, Math.max(1, Number(e.target.value) || 1)) })}
              className="filter-number"
            />
            % или не сдано
          </label>

          <label className="filter-check" title={onlyProblems ? "Не действует вместе с «Только проблемные»" : undefined}>
            <input
              type="checkbox"
              checked={hideEmpty}
              disabled={onlyProblems}
              onChange={(e) => update({ hideEmpty: e.target.checked })}
            />{" "}
            Скрыть строки без данных
          </label>

          {view === "groups" && (
            <input placeholder="Поиск по коду группы" value={groupQuery} onChange={(e) => setGroupQuery(e.target.value)} />
          )}

          <button
            className="link-btn"
            disabled={isDefault}
            onClick={() => {
              onChange(defaultSummaryFilters());
              setGroupQuery("");
              setSort(null);
            }}
          >
            Сбросить
          </button>
        </div>
      </div>

      <div className="toolbar">
        {(Object.keys(VIEW_LABELS) as View[]).map((v) => (
          <button key={v} className={view === v ? "active" : ""} onClick={() => changeView(v)}>
            {VIEW_LABELS[v]}
          </button>
        ))}
      </div>

      <p className="hint">
        «Учтено» — студенты тех групп, что сдали день; несданные группы в «Прибыли» не попадают. «{pairLabel}» —
        группы, у которых куратор указал эту пару первой (дни без указанной пары в срез не входят).
        {view === "period" && " За период числа — в студенто-днях."} Столбцы кодов, «только проблемные» и сортировка
        действуют только на экране; в Excel попадают период, отделение, курс, группа и пара.
      </p>

      {rangeInvalid && <div className="error-text">Дата начала позже даты окончания</div>}
      {error && !rangeInvalid && <div className="error-text">{error}</div>}
      {loading && <p className="hint">Загрузка…</p>}

      {data && !rangeInvalid && view === "daily" && (
        <div className="table-scroll">
          <table className="dash-table summary-table">
            <thead>
              <tr>
                <SortTh label="Дата" sortKey="date" sort={sort} onSort={toggleSort} />
                <SortTh label="Отделение" sortKey="department" sort={sort} onSort={toggleSort} />
                <SortTh label="Срез" sortKey="slice" sort={sort} onSort={toggleSort} />
                <SortTh label="Групп сдали" sortKey="groups_submitted" sort={sort} onSort={toggleSort} />
                <SortTh label="Численность" sortKey="headcount" sort={sort} onSort={toggleSort} />
                <SortTh label="Учтено" sortKey="counted" sort={sort} onSort={toggleSort} />
                <SortTh label="Прибыли" sortKey="present" sort={sort} onSort={toggleSort} />
                <SortTh label="Отсутствуют" sortKey="absent" sort={sort} onSort={toggleSort} />
                <SortTh label="%" sortKey="percent" sort={sort} onSort={toggleSort} />
                {codeHeaders()}
              </tr>
            </thead>
            <tbody>
              {dailyLines.map((line) => lineRow(line, true))}
              {dailyLines.length === 0 && (
                <tr>
                  <td colSpan={9 + visibleCodes.length}>Нет строк под выбранные фильтры.</td>
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
                <SortTh label="Отделение" sortKey="department" sort={sort} onSort={toggleSort} />
                <SortTh label="Срез" sortKey="slice" sort={sort} onSort={toggleSort} />
                <SortTh label="Групп-дней сдано" sortKey="groups_submitted" sort={sort} onSort={toggleSort} />
                <SortTh label="В списках" sortKey="headcount" sort={sort} onSort={toggleSort} />
                <SortTh label="Учтено" sortKey="counted" sort={sort} onSort={toggleSort} />
                <SortTh label="Прибыли" sortKey="present" sort={sort} onSort={toggleSort} />
                <SortTh label="Отсутствуют" sortKey="absent" sort={sort} onSort={toggleSort} />
                <SortTh label="%" sortKey="percent" sort={sort} onSort={toggleSort} />
                {codeHeaders()}
              </tr>
            </thead>
            <tbody>
              {periodLines.map((line) => lineRow(line, false))}
              {periodLines.length === 0 && (
                <tr>
                  <td colSpan={8 + visibleCodes.length}>Нет строк под выбранные фильтры.</td>
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
                <SortTh label="Дата" sortKey="date" sort={sort} onSort={toggleSort} />
                <SortTh label="Группа" sortKey="group" sort={sort} onSort={toggleSort} />
                <SortTh label="Курс" sortKey="course" sort={sort} onSort={toggleSort} />
                <SortTh label="Численность" sortKey="headcount" sort={sort} onSort={toggleSort} />
                <SortTh label="Сдан" sortKey="submitted" sort={sort} onSort={toggleSort} />
                <SortTh label="Прибыли" sortKey="present" sort={sort} onSort={toggleSort} />
                <SortTh label="Отсутствуют" sortKey="absent" sort={sort} onSort={toggleSort} />
                <SortTh label="%" sortKey="percent" sort={sort} onSort={toggleSort} />
                <SortTh label="К какой паре" sortKey="pair" sort={sort} onSort={toggleSort} />
                {codeHeaders()}
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
                  <td data-label="К какой паре">{r.is_submitted ? (r.first_period ?? "не указана") : "—"}</td>
                  {visibleCodes.map((c) => (
                    <td key={c.code} data-label={c.name}>
                      {r.is_submitted ? (r.by_code[c.code] ?? 0) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
              {groupRows.length === 0 && (
                <tr>
                  <td colSpan={9 + visibleCodes.length}>Нет строк под выбранные фильтры.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
