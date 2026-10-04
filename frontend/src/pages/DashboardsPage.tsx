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

function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toIso(d);
}

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
  const [dayRows, setDayRows] = useState<DayOverviewRow[]>([]);

  const [dateFrom, setDateFrom] = useState(daysAgoIso(14));
  const [dateTo, setDateTo] = useState(todayIso());
  const [dynamicsPoints, setDynamicsPoints] = useState<DynamicsPoint[]>([]);

  const [riskRows, setRiskRows] = useState<RiskStudentRow[]>([]);
  const [disciplineRows, setDisciplineRows] = useState<CuratorDisciplineRow[]>([]);

  const [courseFilter, setCourseFilter] = useState<number | "all">("all");
  const [openDisciplineGroupId, setOpenDisciplineGroupId] = useState<number | null>(null);

  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [assigningGroupId, setAssigningGroupId] = useState<number | null>(null);
  const vacantGroups = useMemo(() => groups.filter((g) => g.is_active && !g.curator_name), [groups]);

  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [exportDepartmentId, setExportDepartmentId] = useState<number | "all">("all");
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
  const visibleDayRows = useMemo(
    () => (courseFilter === "all" ? dayRows : dayRows.filter((r) => r.course === courseFilter)),
    [dayRows, courseFilter],
  );

  useEffect(() => {
    if (tab !== "day") return;
    setLoading(true);
    api
      .get<DayOverviewRow[]>(`/dashboards/day?date=${date}`)
      .then((rows) => {
        setDayRows(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [tab, date]);

  useEffect(() => {
    if (tab !== "dynamics") return;
    setLoading(true);
    api
      .get<DynamicsPoint[]>(`/dashboards/dynamics?date_from=${dateFrom}&date_to=${dateTo}`)
      .then((points) => {
        setDynamicsPoints(points);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [tab, dateFrom, dateTo]);

  useEffect(() => {
    if (tab !== "risk") return;
    setLoading(true);
    api
      .get<RiskStudentRow[]>(`/dashboards/risk-students?as_of_date=${date}`)
      .then((rows) => {
        setRiskRows(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [tab, date]);

  useEffect(() => {
    if (tab !== "discipline") return;
    setLoading(true);
    api
      .get<CuratorDisciplineRow[]>(`/dashboards/curator-discipline?date_from=${dateFrom}&date_to=${dateTo}`)
      .then((rows) => {
        setDisciplineRows(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [tab, dateFrom, dateTo]);

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
    const deptParam = canFilterDepartment && exportDepartmentId !== "all" ? `&department_id=${exportDepartmentId}` : "";
    const query =
      tab === "summary"
        ? summaryExportParams(summaryFilters, canFilterDepartment)
        : `date_from=${exportDateFrom}&date_to=${exportDateTo}${deptParam}`;
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
            onChange={(e) => setExportDepartmentId(e.target.value === "all" ? "all" : Number(e.target.value))}
            title="Отделение для свода и экспорта"
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
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          {tab === "day" && (
            <select value={courseFilter} onChange={(e) => setCourseFilter(e.target.value === "all" ? "all" : Number(e.target.value))}>
              <option value="all">Все курсы</option>
              {courses.map((c) => (
                <option key={c} value={c}>
                  Курс {c}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {(tab === "dynamics" || tab === "discipline") && (
        <div className="toolbar">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <span>—</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      )}

      {tab === "day" && (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Группа</th>
              <th>Курс</th>
              <th>Ответственный</th>
              <th>В списке</th>
              <th>Пришло</th>
              <th>Опоздало</th>
              <th>Отс. уваж.</th>
              <th>Отс. неуваж.</th>
              <th>%</th>
              <th>Сдано</th>
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
          </tbody>
        </table>
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
          <table className="dash-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>В списке</th>
                <th>Присутствовало</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {dynamicsPoints.map((p) => (
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
          </table>
        </>
      )}

      {tab === "risk" && (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Студент</th>
              <th>Группа</th>
              <th>Пропусков подряд</th>
            </tr>
          </thead>
          <tbody>
            {riskRows.map((r) => (
              <tr key={r.student_id} className="risk-row">
                <td>
                  <Link to={`/students/${r.student_id}`} className="link-btn">
                    {r.full_name}
                  </Link>
                </td>
                <td>{r.group_code}</td>
                <td>{r.streak}</td>
              </tr>
            ))}
            {riskRows.length === 0 && (
              <tr>
                <td colSpan={3}>Нет студентов группы риска на выбранную дату.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      {tab === "discipline" && isDeptHead && (
        <p className="hint">Нажмите на строку, чтобы увидеть по дням, во сколько сдавался день и кем.</p>
      )}

      {tab === "discipline" && (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Группа</th>
              <th>Курс</th>
              <th>Ответственный</th>
              <th>Вовремя</th>
              <th>С опозданием</th>
              <th>Не сдано</th>
              <th>Всего учебных дней</th>
            </tr>
          </thead>
          <tbody>
            {disciplineRows.map((r) => (
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
          </tbody>
        </table>
      )}

      {tab === "vacant" && (
        <>
          <p className="hint">
            Пока куратор не назначен, отмечать посещаемость в группе некому: в витринах она будет значиться как
            «не сдано». Назначьте куратора или заместителя, чтобы группа заработала как обычно.
          </p>
          <table className="dash-table">
            <thead>
              <tr>
                <th>Группа</th>
                <th>Курс</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {vacantGroups.map((g) => (
                <tr key={g.id} className="not-submitted-row">
                  <td>{g.code}</td>
                  <td>{g.course}</td>
                  <td>
                    <button onClick={() => setAssigningGroupId(g.id)}>Назначить куратора</button>
                  </td>
                </tr>
              ))}
              {vacantGroups.length === 0 && (
                <tr>
                  <td colSpan={3}>Вакантных групп нет — у каждой есть куратор.</td>
                </tr>
              )}
            </tbody>
          </table>
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
