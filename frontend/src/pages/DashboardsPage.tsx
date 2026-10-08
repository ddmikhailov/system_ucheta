import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { downloadFile } from "../api/client";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import AssignCuratorModal from "../components/AssignCuratorModal";
import AttendanceSummaryView from "../components/AttendanceSummary";
import {
  filtersToParams,
  initialSummaryFilters,
  sanitizeSummaryFilters,
  saveFilters,
  summaryExportParams,
} from "../utils/summaryFilters";
import type { SummaryFilters } from "../utils/summaryFilters";
import CuratorDaysModal from "../components/CuratorDaysModal";
import type {
  CuratorDisciplineRow,
  DayOverviewRow,
  DepartmentAdmin,
  DynamicsPoint,
  RiskStudentRow,
  StudyGroupAdmin,
  UserAdmin,
} from "../api/types";
import { COLLEGE_WIDE_ROLES, CURATOR_CAPABLE_ROLES, DEPARTMENT_SCOPED_ROLES, DOSSIER_STAFF_ROLES, inRoles } from "../constants/roles";
import { formatDateRu, toIso, todayIso } from "../utils/date";
import { formatPercent } from "../utils/percent";
import { filterByQuery } from "../utils/searchMatch";
import { nextSort, sortRows } from "../utils/tableView";
import type { SortState } from "../utils/tableView";
import ResultsBar from "../components/dashboards/ResultsBar";
import SortHeader from "../components/dashboards/SortHeader";

function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toIso(d);
}

type DayKey = "code" | "course" | "responsible" | "in_list" | "present" | "late" | "excused" | "unexcused" | "percent" | "submitted";
type DynKey = "date" | "in_list" | "present" | "percent";
type RiskKey = "name" | "group" | "percent" | "absent";
type DiscKey = "code" | "course" | "responsible" | "on_time" | "late" | "missed" | "total";
type VacantKey = "code" | "course";
type DayStatus = "all" | "missing" | "on_time" | "late";

const NO_CURATOR = "нет куратора";

type Tab = "day" | "summary" | "dynamics" | "risk" | "discipline" | "vacant";
const TABS: Tab[] = ["day", "summary", "dynamics", "risk", "discipline", "vacant"];

export default function DashboardsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  // Зав. отделением и тьютор видят только своё отделение.
  const isDeptHead = inRoles(user?.role, DEPARTMENT_SCOPED_ROLES);
  // Админ/тьютор/учебный отдел видят весь колледж и могут сузить экспорт до
  // одного отделения; зав. отделением и так видит только своё (см. TODO.md 4).
  const isStaff = inRoles(user?.role, DOSSIER_STAFF_ROLES);
  const canFilterDepartment = inRoles(user?.role, COLLEGE_WIDE_ROLES);

  // Вкладка и фильтры «Свода» живут в адресной строке — ссылкой можно поделиться,
  // а при обычном заходе подставляется последний сохранённый выбор.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(tabFromUrl && TABS.includes(tabFromUrl) ? tabFromUrl : "day");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [date, setDate] = useState(todayIso());
  // Счётчик перезагрузки: кнопка «Обновить» и возврат на вкладку браузера заново
  // запрашивают данные — статусы сдачи дня меняются, пока страница открыта.
  const [reloadKey, setReloadKey] = useState(0);
  const [dayRows, setDayRows] = useState<DayOverviewRow[]>([]);

  const [dateFrom, setDateFrom] = useState(daysAgoIso(14));
  const [dateTo, setDateTo] = useState(todayIso());
  const [dynamicsPoints, setDynamicsPoints] = useState<DynamicsPoint[]>([]);

  const [riskRows, setRiskRows] = useState<RiskStudentRow[]>([]);
  const [disciplineRows, setDisciplineRows] = useState<CuratorDisciplineRow[]>([]);

  const [courseFilter, setCourseFilter] = useState<number | "all">("all");
  // Фильтры и сортировки таблиц: считаются на странице по уже загруженным строкам.
  const [dayQuery, setDayQuery] = useState("");
  const [dayStatus, setDayStatus] = useState<DayStatus>("all");
  const [dayOnlyAbsent, setDayOnlyAbsent] = useState(false);
  const [daySort, setDaySort] = useState<SortState<DayKey> | null>(null);
  const [dynOnlyData, setDynOnlyData] = useState(false);
  const [dynBelow, setDynBelow] = useState("");
  const [dynSort, setDynSort] = useState<SortState<DynKey> | null>(null);
  const [riskQuery, setRiskQuery] = useState("");
  const [riskGroup, setRiskGroup] = useState<number | "all">("all");
  const [riskBelow, setRiskBelow] = useState("");
  const [riskSort, setRiskSort] = useState<SortState<RiskKey> | null>(null);
  const [discQuery, setDiscQuery] = useState("");
  const [discCourse, setDiscCourse] = useState<number | "all">("all");
  const [discOnlyMissed, setDiscOnlyMissed] = useState(false);
  const [discSort, setDiscSort] = useState<SortState<DiscKey> | null>(null);
  const [vacantQuery, setVacantQuery] = useState("");
  const [vacantCourse, setVacantCourse] = useState<number | "all">("all");
  const [vacantSort, setVacantSort] = useState<SortState<VacantKey> | null>(null);
  const [openDisciplineGroupId, setOpenDisciplineGroupId] = useState<number | null>(null);

  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [assigningGroupId, setAssigningGroupId] = useState<number | null>(null);
  const vacantGroups = useMemo(() => groups.filter((g) => g.is_active && !g.curator_name), [groups]);
  const vacantCourses = useMemo(() => Array.from(new Set(vacantGroups.map((g) => g.course))).sort((a, b) => a - b), [vacantGroups]);
  const vacantFiltered = vacantQuery.trim() !== "" || vacantCourse !== "all";
  const visibleVacant = useMemo(() => {
    let rows = vacantGroups;
    if (vacantCourse !== "all") rows = rows.filter((g) => g.course === vacantCourse);
    rows = filterByQuery(rows, vacantQuery, (g) => g.code);
    return sortRows(rows, vacantSort, { code: (g) => g.code, course: (g) => g.course });
  }, [vacantGroups, vacantCourse, vacantQuery, vacantSort]);

  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  // Выбранное отделение (для админа/тьютора/учебного отдела) сужает все вкладки и экспорт.
  const [exportDepartmentId, setExportDepartmentId] = useState<number | "all">("all");
  const deptQuery = canFilterDepartment && exportDepartmentId !== "all" ? `&department_id=${exportDepartmentId}` : "";
  // Фильтры «Свода» живут здесь, чтобы выгрузка в Excel брала тот же отбор.
  const [rawSummaryFilters, setSummaryFilters] = useState<SummaryFilters>(() => initialSummaryFilters(searchParams));
  const [exportError, setExportError] = useState<string | null>(null);

  // Запомненная/пришедшая по ссылке группа или отделение могут быть недоступны.
  const summaryFilters = useMemo(
    () => sanitizeSummaryFilters(rawSummaryFilters, groups, canFilterDepartment),
    [rawSummaryFilters, groups, canFilterDepartment],
  );

  useEffect(() => saveFilters(summaryFilters), [summaryFilters]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") setReloadKey((k) => k + 1);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  useEffect(() => {
    if (tab === "summary") {
      const params = filtersToParams(summaryFilters, false);
      params.set("tab", "summary");
      setSearchParams(params, { replace: true });
    } else {
      setSearchParams({ tab }, { replace: true });
    }
  }, [tab, summaryFilters, setSearchParams]);

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

  const riskBelowNum = riskBelow.trim() === "" ? null : Number(riskBelow);
  const riskFiltered = riskQuery.trim() !== "" || riskGroup !== "all" || riskBelowNum !== null;
  const riskGroups = useMemo(() => {
    const byId = new Map<number, string>();
    for (const r of riskRows) byId.set(r.study_group_id, r.group_code);
    return [...byId].sort((a, b) => a[1].localeCompare(b[1], "ru", { numeric: true }));
  }, [riskRows]);
  const visibleRisk = useMemo(() => {
    let rows = riskRows;
    if (riskGroup !== "all") rows = rows.filter((r) => r.study_group_id === riskGroup);
    if (riskBelowNum !== null && !Number.isNaN(riskBelowNum)) rows = rows.filter((r) => r.attendance_percent < riskBelowNum);
    rows = filterByQuery(rows, riskQuery, (r) => `${r.full_name} ${r.group_code}`);
    return sortRows(rows, riskSort, {
      name: (r) => r.full_name, group: (r) => r.group_code, percent: (r) => r.attendance_percent, absent: (r) => r.absent,
    });
  }, [riskRows, riskGroup, riskBelowNum, riskQuery, riskSort]);

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

  function resetAllFilters() {
    resetDayFilters();
    setDynOnlyData(false);
    setDynBelow("");
    setRiskQuery("");
    setRiskGroup("all");
    setRiskBelow("");
    setDiscQuery("");
    setDiscCourse("all");
    setDiscOnlyMissed(false);
  }

  useEffect(() => {
    if (tab !== "day") return;
    let cancelled = false;
    setLoading(true);
    api
      .get<DayOverviewRow[]>(`/dashboards/day?date=${date}${deptQuery}`)
      .then((rows) => {
        if (cancelled) return;
        setDayRows(rows);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      setLoading(false);
    };
  }, [tab, date, deptQuery, reloadKey]);

  useEffect(() => {
    if (tab !== "dynamics") return;
    let cancelled = false;
    setLoading(true);
    api
      .get<DynamicsPoint[]>(`/dashboards/dynamics?date_from=${dateFrom}&date_to=${dateTo}${deptQuery}`)
      .then((points) => {
        if (cancelled) return;
        setDynamicsPoints(points);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      setLoading(false);
    };
  }, [tab, dateFrom, dateTo, deptQuery, reloadKey]);

  useEffect(() => {
    if (tab !== "risk") return;
    let cancelled = false;
    setLoading(true);
    api
      .get<RiskStudentRow[]>(`/dashboards/risk-students?as_of_date=${date}${deptQuery}`)
      .then((rows) => {
        if (cancelled) return;
        setRiskRows(rows);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      setLoading(false);
    };
  }, [tab, date, deptQuery, reloadKey]);

  useEffect(() => {
    if (tab !== "discipline") return;
    let cancelled = false;
    setLoading(true);
    api
      .get<CuratorDisciplineRow[]>(`/dashboards/curator-discipline?date_from=${dateFrom}&date_to=${dateTo}${deptQuery}`)
      .then((rows) => {
        if (cancelled) return;
        setDisciplineRows(rows);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Ошибка загрузки");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      setLoading(false);
    };
  }, [tab, dateFrom, dateTo, deptQuery, reloadKey]);

  function loadVacantGroups() {
    api
      .get<StudyGroupAdmin[]>("/admin/groups")
      .then((rows) => {
        setGroups(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка загрузки"));
    api
      .get<UserAdmin[]>("/admin/users")
      .then((us) => setCurators(us.filter((u) => u.is_active && (CURATOR_CAPABLE_ROLES.includes(u.role)))))
      .catch(() => setCurators([]));
  }

  useEffect(() => {
    // Грузим сразу, чтобы счётчик в вкладке был виден и без переключения на неё.
    loadVacantGroups();
    if (canFilterDepartment) {
      api.get<DepartmentAdmin[]>("/admin/departments").then(setDepartments).catch(() => setDepartments([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Экспорт раньше всегда брал диапазон вкладки "Динамика", даже если открыта
  // "День"/"Группа риска" — там теперь берём выбранный день (see TODO.md 4).
  const exportDateFrom = tab === "summary" ? summaryFilters.dateFrom : tab === "day" || tab === "risk" ? date : dateFrom;
  const exportDateTo = tab === "summary" ? summaryFilters.dateTo : tab === "day" || tab === "risk" ? date : dateTo;

  function handleExport() {
    setExportError(null);
    const query =
      tab === "summary"
        ? summaryExportParams(summaryFilters, canFilterDepartment)
        : `date_from=${exportDateFrom}&date_to=${exportDateTo}${deptQuery}`;
    downloadFile(
      `/export/excel?${query}`,
      `itog_${exportDateFrom}_${exportDateTo}.xlsx`,
    ).catch((err) => setExportError(err instanceof ApiError ? err.message : "Не удалось скачать файл"));
  }

  return (
    <div>
      <div className="tabs">
        <button className={tab === "day" ? "active" : ""} onClick={() => setTab("day")}>
          {isDeptHead ? "День по отделению" : "День по колледжу"}
        </button>
        <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>
          Свод
        </button>
        <button className={tab === "dynamics" ? "active" : ""} onClick={() => setTab("dynamics")}>
          Динамика
        </button>
        <button className={tab === "risk" ? "active" : ""} onClick={() => setTab("risk")}>
          Группа риска
        </button>
        {!isStaff && (
          <button className={tab === "discipline" ? "active" : ""} onClick={() => setTab("discipline")}>
            Дисциплина кураторов
          </button>
        )}
        {!isStaff && (
          <button className={tab === "vacant" ? "active" : ""} onClick={() => setTab("vacant")}>
            Вакантные группы{vacantGroups.length > 0 ? ` (${vacantGroups.length})` : ""}
          </button>
        )}
        {canFilterDepartment && tab !== "summary" && (
          <select
            value={exportDepartmentId}
            onChange={(e) => {
              setExportDepartmentId(e.target.value === "all" ? "all" : Number(e.target.value));
              resetAllFilters();
              setOpenDisciplineGroupId(null);
            }}
            title="Отделение: данные на вкладках и экспорт"
          >
            <option value="all">Весь колледж</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        )}
        <button className="link-btn" onClick={handleExport}>
          Экспорт в Excel ({formatDateRu(exportDateFrom)}–{formatDateRu(exportDateTo)})
        </button>
      </div>

      {exportError && <div className="error-text">{exportError}</div>}
      {error && <div className="error-text">{error}</div>}
      {loading && <p className="hint">Загрузка…</p>}

      {(tab === "day" || tab === "risk") && (
        <div className="toolbar">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Дата" />
          <button className="link-btn" onClick={() => setReloadKey((k) => k + 1)} title="Запросить данные заново">
            Обновить
          </button>
        </div>
      )}

      {(tab === "dynamics" || tab === "discipline") && (
        <div className="toolbar">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} aria-label="Период с" />
          <span>—</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} aria-label="Период по" />
        </div>
      )}

      {tab === "day" && (
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
      )}

      {tab === "day" && (
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
      )}

      {tab === "summary" && (
        <AttendanceSummaryView
          filters={summaryFilters}
          onChange={setSummaryFilters}
          canFilterDepartment={canFilterDepartment}
          departments={departments}
          groups={groups}
        />
      )}

      {tab === "dynamics" && (
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
      )}

      {tab === "risk" && (
        <>
          <div className="toolbar toolbar--filters">
            <input type="search" value={riskQuery} onChange={(e) => setRiskQuery(e.target.value)} placeholder="Студент или группа" aria-label="Поиск по студенту или группе" />
            <select aria-label="Группа" value={riskGroup} onChange={(e) => setRiskGroup(e.target.value === "all" ? "all" : Number(e.target.value))}>
              <option value="all">Все группы</option>
              {riskGroups.map(([id, code]) => (
                <option key={id} value={id}>{code}</option>
              ))}
            </select>
            <input type="number" min={0} max={100} value={riskBelow} onChange={(e) => setRiskBelow(e.target.value)} placeholder="Посещаемость ниже, %" aria-label="Посещаемость ниже, %" />
          </div>
          <ResultsBar shown={visibleRisk.length} total={riskRows.length} filtered={riskFiltered} onReset={() => { setRiskQuery(""); setRiskGroup("all"); setRiskBelow(""); }} />
        </>
      )}

      {tab === "risk" && (
        <div className="table-scroll"><table className="dash-table">
          <thead>
            <tr>
              <SortHeader label="Студент" sortKey="name" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
              <SortHeader label="Группа" sortKey="group" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
              <SortHeader label="Посещаемость с начала семестра" sortKey="percent" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
              <SortHeader label="Пропущено дней" sortKey="absent" sort={riskSort} onSort={(k) => setRiskSort((s) => nextSort(s, k))} />
            </tr>
          </thead>
          <tbody>
            {visibleRisk.map((r) => (
              <tr key={r.student_id} className="risk-row">
                <td>
                  <Link to={`/students/${r.student_id}`} className="link-btn">
                    {r.full_name}
                  </Link>
                </td>
                <td>{r.group_code}</td>
                <td>{formatPercent(r.attendance_percent)}</td>
                <td>
                  {r.absent} из {r.days}
                </td>
              </tr>
            ))}
            {visibleRisk.length === 0 && (
              <tr>
                <td colSpan={4}>{riskRows.length === 0 ? "Нет студентов группы риска на выбранную дату." : "Под выбранные фильтры ничего не подошло."}</td>
              </tr>
            )}
          </tbody>
        </table></div>
      )}

      {tab === "discipline" && isDeptHead && (
        <p className="hint">Нажмите на строку, чтобы увидеть по дням, во сколько сдавался день и кем.</p>
      )}

      {tab === "discipline" && (
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
      )}

      {tab === "discipline" && (
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
      )}

      {tab === "vacant" && (
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
                    <button onClick={() => setAssigningGroupId(g.id)}>Назначить куратора</button>
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
      )}

      {openDisciplineGroupId !== null && (
        <CuratorDaysModal
          studyGroupId={openDisciplineGroupId}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onClose={() => setOpenDisciplineGroupId(null)}
        />
      )}

      {assigningGroupId !== null && (
        <AssignCuratorModal
          groupId={assigningGroupId}
          curators={curators}
          onClose={() => setAssigningGroupId(null)}
          onSaved={() => {
            setAssigningGroupId(null);
            loadVacantGroups();
          }}
        />
      )}
    </div>
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

function PercentBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    // День не сдан — раньше это молча считалось за 100% (см. TODO.md 3).
    return <span className="hint">—</span>;
  }
  const color = value >= 95 ? "var(--ok)" : value >= 85 ? "var(--warn)" : "var(--danger)";
  const textColor = value >= 95 ? "var(--ok)" : value >= 85 ? "var(--warn-ink)" : "var(--danger)";
  return (
    <div className="percent-bar">
      <div className="percent-bar__track">
        <div className="percent-bar__fill" style={{ width: `${Math.min(value, 100)}%`, background: color }} />
      </div>
      <span className="percent-bar__value" style={{ color: textColor }}>
        {value.toFixed(1)}%
      </span>
    </div>
  );
}
