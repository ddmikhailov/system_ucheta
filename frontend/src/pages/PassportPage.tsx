import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, downloadFile } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { COLLEGE_WIDE_ROLES, DOSSIER_AUDIT_ROLES, inRoles } from "../constants/roles";
import type { DepartmentAdmin } from "../api/types";
import { TabBar, TabPanel } from "../components/Tabs";
import ResultsBar from "../components/dashboards/ResultsBar";
import SortHeader from "../components/dashboards/SortHeader";
import { filterByQuery } from "../utils/searchMatch";
import { nextSort, sortRows, type SortState, type SortValue } from "../utils/tableView";

interface SummaryRow {
  group_id: number;
  group_code: string;
  course: number;
  department_name: string;
  students_total: number;
  minors: number;
  budget: number;
  contract: number;
  no_guardians: number;
  dossier_empty: number;
  counts: Record<string, number | null>;
}

interface Summary {
  special_available: boolean;
  categories: { key: string; title: string }[];
  rows: SummaryRow[];
  totals: SummaryRow;
}

interface Category {
  key: string;
  title: string;
  count: number | null;
  names: string[];
}

interface GroupPassport {
  group_id: number;
  group_code: string;
  course: number;
  department_name: string;
  students_total: number;
  minors: number;
  adults: number;
  birth_date_missing: number;
  budget: number;
  contract: number;
  funding_missing: number;
  no_guardians: number;
  dossier_empty: number;
  special_available: boolean;
  categories: Category[];
}

const fmt = (n: number | null | undefined) => (n === null || n === undefined ? "—" : String(n));

type Focus = "all" | "no_guardians" | "dossier_empty" | "minors" | "contract";
const FOCUS_LABELS: Record<Focus, string> = {
  all: "Все группы",
  no_guardians: "Есть студенты без представителей",
  dossier_empty: "Есть незаполненные досье",
  minors: "Есть несовершеннолетние",
  contract: "Есть договорники",
};

function matchesFocus(r: SummaryRow, focus: Focus): boolean {
  switch (focus) {
    case "no_guardians": return r.no_guardians > 0;
    case "dossier_empty": return r.dossier_empty > 0;
    case "minors": return r.minors > 0;
    case "contract": return r.contract > 0;
    default: return true;
  }
}

/** Итоги по видимым строкам (когда включены фильтры, итог сервера по всему отделению уже не подходит). */
function sumRows(rows: SummaryRow[], categories: { key: string }[]): SummaryRow {
  const counts: Record<string, number | null> = {};
  for (const c of categories) {
    const values = rows.map((r) => r.counts[c.key]).filter((v): v is number => v !== null && v !== undefined);
    counts[c.key] = values.length === 0 ? null : values.reduce((a, b) => a + b, 0);
  }
  const total = (pick: (r: SummaryRow) => number) => rows.reduce((acc, r) => acc + pick(r), 0);
  return {
    group_id: 0, group_code: "Итого", course: 0, department_name: "",
    students_total: total((r) => r.students_total), minors: total((r) => r.minors), budget: total((r) => r.budget),
    contract: total((r) => r.contract), no_guardians: total((r) => r.no_guardians), dossier_empty: total((r) => r.dossier_empty),
    counts,
  };
}

// Социальный паспорт: сводка из досье по группам и поимённая карточка группы.
// Особые данные берутся из зашифрованного досье — каждый просмотр поимённого
// паспорта попадает в журнал просмотров досье.
function SpecialUnavailable({ technical }: { technical: boolean }) {
  return (
    <p className="hint">
      {technical
        ? "Особые категории недоступны: на сервере не задан ключ шифрования (DOSSIER_ENCRYPTION_KEY)."
        : "Особые категории (здоровье, учёт) сейчас не показываются. Если они нужны, обратитесь к администратору платформы."}
    </p>
  );
}

/** Паспорт одной группы: загрузка и выгрузки. Используется и на странице «Соц. паспорт», и во вкладке группы куратора. */
export function GroupPassportPanel({ groupId }: { groupId: number }) {
  const [passport, setPassport] = useState<GroupPassport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<GroupPassport>(`/passport/group/${groupId}`)
      .then((p) => {
        if (cancelled) return;
        setPassport(p);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Не удалось загрузить паспорт группы");
      });
    return () => {
      cancelled = true;
    };
  }, [groupId]);

  function exportFile(path: string, filename: string) {
    downloadFile(path, filename).catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось скачать файл"));
  }

  // Паспорт прошлой группы не показываем, пока грузится новый.
  const shown = passport && passport.group_id === groupId ? passport : null;
  return (
    <>
      {error && <div className="error-text">{error}</div>}
      {shown === null && !error && <p className="hint">Загрузка…</p>}
      {shown && (
        <GroupView
          passport={shown}
          onExport={() => exportFile(`/passport/export?group_id=${groupId}`, "social_passport.xlsx")}
          onExportWord={() => exportFile(`/passport/group/${groupId}/docx`, `Социальный_паспорт_${shown.group_code}.docx`)}
        />
      )}
    </>
  );
}

export default function PassportPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const groupId = searchParams.get("group");
  const [departmentId, setDepartmentId] = useState("");
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [course, setCourse] = useState<number | "all">("all");
  const [focus, setFocus] = useState<Focus>("all");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<SortState<string> | null>(null);

  const canFilterDepartment = inRoles(user?.role, COLLEGE_WIDE_ROLES);
  // Причину (нет ключа шифрования на сервере) знать нужно администратору; остальным — что делать.
  const technical = inRoles(user?.role, DOSSIER_AUDIT_ROLES);

  useEffect(() => {
    if (!canFilterDepartment) return;
    api.get<DepartmentAdmin[]>("/admin/departments").then(setDepartments).catch(() => setDepartments([]));
  }, [canFilterDepartment, user]);

  useEffect(() => {
    if (groupId) return;
    const query = departmentId ? `?department_id=${departmentId}` : "";
    api
      .get<Summary>(`/passport/summary${query}`)
      .then((s) => {
        setSummary(s);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить паспорт"));
  }, [departmentId, groupId]);

  const rows = useMemo(() => summary?.rows ?? [], [summary]);
  const courses = useMemo(() => [...new Set(rows.map((r) => r.course))].sort((a, b) => a - b), [rows]);
  const filtered = query.trim() !== "" || course !== "all" || focus !== "all" || category !== "";
  const visible = useMemo(() => {
    let list = rows.filter((r) => (course === "all" || r.course === course) && matchesFocus(r, focus));
    if (category) list = list.filter((r) => (r.counts[category] ?? 0) > 0);
    list = filterByQuery(list, query, (r) => `${r.group_code} ${r.department_name}`);
    const getters: Record<string, (r: SummaryRow) => SortValue> = {
      group: (r) => r.group_code, students: (r) => r.students_total, minors: (r) => r.minors,
      budget: (r) => r.budget, no_guardians: (r) => r.no_guardians, dossier_empty: (r) => r.dossier_empty,
    };
    for (const c of summary?.categories ?? []) getters[`cat:${c.key}`] = (r) => r.counts[c.key];
    return sortRows(list, sort, getters);
  }, [rows, course, focus, category, query, sort, summary]);
  const totals = summary && (filtered ? sumRows(visible, summary.categories) : summary.totals);
  function resetFilters() {
    setQuery("");
    setCourse("all");
    setFocus("all");
    setCategory("");
    setSort(null);
  }
  const onSort = (k: string) => setSort((cur) => nextSort(cur, k));

  function exportFile(path: string, filename: string) {
    downloadFile(path, filename).catch((err) =>
      setError(err instanceof ApiError ? err.message : "Не удалось скачать файл")
    );
  }
  const exportExcel = (path: string) => exportFile(path, "social_passport.xlsx");

  if (groupId) {
    return (
      <div>
        <p>
          <button className="link-btn" onClick={() => setSearchParams({})}>
            ← К сводке по группам
          </button>
        </p>
        <GroupPassportPanel groupId={Number(groupId)} />
      </div>
    );
  }

  return (
    <div>
      <div className="toolbar">
        {canFilterDepartment && (
          <select aria-label="Отделение" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
            <option value="">Весь колледж</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        )}
        <button
          className="link-btn"
          onClick={() => exportExcel(`/passport/export${departmentId ? `?department_id=${departmentId}` : ""}`)}
        >
          Экспорт сводки в Excel
        </button>
      </div>
      {summary && rows.length > 0 && (
        <>
          <div className="toolbar toolbar--filters">
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Группа или отделение" aria-label="Поиск по группе или отделению" />
            <select aria-label="Курс" value={course} onChange={(e) => setCourse(e.target.value === "all" ? "all" : Number(e.target.value))}>
              <option value="all">Все курсы</option>
              {courses.map((c) => (
                <option key={c} value={c}>{c} курс</option>
              ))}
            </select>
            <select aria-label="Что показать" value={focus} onChange={(e) => setFocus(e.target.value as Focus)}>
              {(Object.keys(FOCUS_LABELS) as Focus[]).map((k) => (
                <option key={k} value={k}>{FOCUS_LABELS[k]}</option>
              ))}
            </select>
            <select aria-label="Особая категория" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Любые категории</option>
              {summary.categories.map((c) => (
                <option key={c.key} value={c.key}>Есть: {c.title}</option>
              ))}
            </select>
          </div>
          <ResultsBar shown={visible.length} total={rows.length} filtered={filtered} onReset={resetFilters} />
        </>
      )}
      {error && <div className="error-text">{error}</div>}
      {!summary && !error && <p className="hint">Загрузка…</p>}
      {summary && (
        <>
          {!summary.special_available && (
            <SpecialUnavailable technical={technical} />
          )}
          {rows.length === 0 ? (
            <p className="hint">Нет доступных групп.</p>
          ) : visible.length === 0 ? (
            <p className="hint">Под выбранные условия ни одна группа не подошла.</p>
          ) : (
            <div className="table-scroll"><table className="dash-table">
              <thead>
                <tr>
                  <SortHeader label="Группа" sortKey="group" sort={sort} onSort={onSort} />
                  <SortHeader label="Студентов" sortKey="students" sort={sort} onSort={onSort} />
                  <SortHeader label="Несоверш." sortKey="minors" sort={sort} onSort={onSort} />
                  <SortHeader label="Бюджет / договор" sortKey="budget" sort={sort} onSort={onSort} />
                  <SortHeader label="Без представителей" sortKey="no_guardians" sort={sort} onSort={onSort} />
                  <SortHeader label="Досье пустое" sortKey="dossier_empty" sort={sort} onSort={onSort} />
                  {summary.categories.map((c) => (
                    <SortHeader key={c.key} label={c.title} sortKey={`cat:${c.key}`} sort={sort} onSort={onSort} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...visible, ...(visible.length > 1 && totals ? [totals] : [])].map((r, i, all) => {
                  const isTotal = r.group_id === 0 && i === all.length - 1 && visible.length > 1;
                  return (
                    <tr
                      key={r.group_id}
                      className={isTotal ? "" : "clickable-row"}
                      style={isTotal ? { fontWeight: 600 } : undefined}
                      onClick={isTotal ? undefined : () => setSearchParams({ group: String(r.group_id) })}
                      title={isTotal ? undefined : "Открыть паспорт группы"}
                    >
                      <td data-label="Группа">{r.group_code}</td>
                      <td data-label="Студентов">{r.students_total}</td>
                      <td data-label="Несоверш.">{r.minors}</td>
                      <td data-label="Бюджет / договор">
                        {r.budget} / {r.contract}
                      </td>
                      <td data-label="Без представителей">{r.no_guardians}</td>
                      <td data-label="Досье пустое">{r.dossier_empty}</td>
                      {summary.categories.map((c) => (
                        <td key={c.key} data-label={c.title}>
                          {fmt(r.counts[c.key])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table></div>
          )}
        </>
      )}
    </div>
  );
}

function GroupView({ passport: p, onExport, onExportWord }: { passport: GroupPassport; onExport: () => void; onExportWord: () => void }) {
  const { user } = useAuth();
  const technical = inRoles(user?.role, DOSSIER_AUDIT_ROLES);
  const [part, setPart] = useState("info");
  const [catQuery, setCatQuery] = useState("");
  const [onlyMarked, setOnlyMarked] = useState(false);
  const [catSort, setCatSort] = useState<SortState<string> | null>(null);
  const shownCategories = useMemo(() => {
    let list = p.categories;
    if (onlyMarked) list = list.filter((c) => (c.count ?? 0) > 0);
    list = filterByQuery(list, catQuery, (c) => `${c.title} ${c.names.join(" ")}`);
    return sortRows(list, catSort, {
      title: (c) => c.title, count: (c) => c.count, names: (c) => (c.names.length > 0 ? c.names[0] : null),
    });
  }, [p.categories, onlyMarked, catQuery, catSort]);
  const catFiltered = onlyMarked || catQuery.trim() !== "";
  const marked = p.categories.filter((c) => (c.count ?? 0) > 0).length;
  return (
    <div className="student-card">
      <div className="student-card__header">
        <h2>
          Социальный паспорт группы {p.group_code}
        </h2>
        <div className="toolbar">
          <button className="btn-secondary" onClick={onExportWord} title="Бланк колледжа: направления профиля, шапка и подписи — можно распечатать или править в Word">
            Экспорт в Word (бланк колледжа)
          </button>
          <button className="btn-secondary" onClick={onExport}>
            Экспорт в Excel
          </button>
        </div>
      </div>
      <TabBar
        tabs={[
          { key: "info", label: "Сведения о группе" },
          { key: "categories", label: "Особые категории", badge: marked || undefined },
        ]}
        active={part}
        onChange={setPart}
        label="Разделы паспорта"
        idPrefix="passport"
        variant="sub"
      />
      <TabPanel idPrefix="passport" tabKey="info" active={part}>
      <dl className="student-card__grid">
        <Item label="Отделение" value={p.department_name} />
        <Item label="Курс" value={String(p.course)} />
        <Item label="Студентов" value={String(p.students_total)} />
        <Item label="Несовершеннолетних / совершеннолетних" value={`${p.minors} / ${p.adults}`} />
        <Item label="Бюджет / договор" value={`${p.budget} / ${p.contract}`} />
        <Item label="Без представителей" value={String(p.no_guardians)} />
        <Item label="Досье не заполнено" value={String(p.dossier_empty)} />
        <Item label="Нет даты рождения" value={String(p.birth_date_missing)} />
      </dl>
      </TabPanel>

      <TabPanel idPrefix="passport" tabKey="categories" active={part}>
      {!p.special_available && (
        <SpecialUnavailable technical={technical} />
      )}
      <div className="toolbar toolbar--filters">
        <input type="search" value={catQuery} onChange={(e) => setCatQuery(e.target.value)} placeholder="Категория или ФИО студента" aria-label="Поиск по категории или студенту" />
        <div className="chip-filter" role="group" aria-label="Показать">
          <button type="button" className={`chip-filter__item${!onlyMarked ? " is-active" : ""}`} aria-pressed={!onlyMarked} onClick={() => setOnlyMarked(false)}>Все категории</button>
          <button type="button" className={`chip-filter__item${onlyMarked ? " is-active" : ""}`} aria-pressed={onlyMarked} onClick={() => setOnlyMarked(true)}>Только с отметками</button>
        </div>
      </div>
      <ResultsBar
        shown={shownCategories.length}
        total={p.categories.length}
        filtered={catFiltered}
        onReset={() => { setCatQuery(""); setOnlyMarked(false); setCatSort(null); }}
      />
      <div className="table-scroll"><table className="dash-table">
        <thead>
          <tr>
            <SortHeader label="Категория" sortKey="title" sort={catSort} onSort={(k) => setCatSort((s) => nextSort(s, k))} />
            <SortHeader label="Человек" sortKey="count" sort={catSort} onSort={(k) => setCatSort((s) => nextSort(s, k))} />
            <SortHeader label="Кто" sortKey="names" sort={catSort} onSort={(k) => setCatSort((s) => nextSort(s, k))} />
          </tr>
        </thead>
        <tbody>
          {shownCategories.length === 0 && (
            <tr><td colSpan={3}>Под выбранные условия ничего не нашлось.</td></tr>
          )}
          {shownCategories.map((c) => (
            <tr key={c.key}>
              <td data-label="Категория">{c.title}</td>
              <td data-label="Человек">{fmt(c.count)}</td>
              <td data-label="Кто">{c.names.length > 0 ? c.names.join(", ") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {p.dossier_empty > 0 && (
        <p className="hint">
          У {p.dossier_empty} студентов досье не заполнено — цифры по категориям неполные, пока данные не внесены.
        </p>
      )}
      </TabPanel>
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="student-card__item">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
