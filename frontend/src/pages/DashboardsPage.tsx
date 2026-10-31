import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
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
import type { DepartmentAdmin, StudyGroupAdmin, UserAdmin } from "../api/types";
import { COLLEGE_WIDE_ROLES, CURATOR_CAPABLE_ROLES, DEPARTMENT_SCOPED_ROLES, DOSSIER_STAFF_ROLES, inRoles } from "../constants/roles";
import { formatDateRu, toIso, todayIso } from "../utils/date";
import { setEntryStateValue } from "../utils/navMemory";
import { useEntryState } from "../hooks/useEntryState";
import DayTab from "../components/dashboards/DayTab";
import DynamicsTab from "../components/dashboards/DynamicsTab";
import RiskTab from "../components/dashboards/RiskTab";
import PracticeTab from "../components/dashboards/PracticeTab";
import DisciplineTab from "../components/dashboards/DisciplineTab";
import { DAY_FILTERS, DISCIPLINE_FILTERS, DYNAMICS_FILTERS, RISK_FILTERS } from "../components/dashboards/dashboardFilters";
import VacantTab from "../components/dashboards/VacantTab";

function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toIso(d);
}

type Tab = "day" | "summary" | "dynamics" | "risk" | "practice" | "discipline" | "vacant";
const TABS: Tab[] = ["day", "summary", "dynamics", "risk", "practice", "discipline", "vacant"];

// Вкладки сами грузят свои строки и держат свои фильтры и сортировки (components/dashboards/*Tab);
// здесь — общее: вкладка, день и период, отделение, экспорт, группы для «Свода» и вакантных групп.
export default function DashboardsPage() {
  const { user } = useAuth();
  const location = useLocation();
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

  const [date, setDate] = useEntryState("date", todayIso());
  // Счётчик перезагрузки: кнопка «Обновить» и возврат на вкладку браузера заново
  // запрашивают данные — статусы сдачи дня меняются, пока страница открыта.
  const [reloadKey, setReloadKey] = useState(0);

  const [dateFrom, setDateFrom] = useEntryState("dateFrom", daysAgoIso(14));
  const [dateTo, setDateTo] = useEntryState("dateTo", todayIso());
  // Смена отделения сбрасывает фильтры вкладок: новое значение пишется в память записи истории,
  // а открытая вкладка пересоздаётся и читает его.
  const [filtersEpoch, setFiltersEpoch] = useState(0);

  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [assigningGroupId, setAssigningGroupId] = useState<number | null>(null);
  const vacantGroups = useMemo(() => groups.filter((g) => g.is_active && !g.curator_name), [groups]);

  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  // Выбранное отделение (для админа/тьютора/учебного отдела) сужает все вкладки и экспорт.
  const [exportDepartmentId, setExportDepartmentId] = useEntryState<number | "all">("exportDepartmentId", "all");
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

  function resetAllFilters() {
    for (const [name, value] of Object.entries({ ...DAY_FILTERS, ...DYNAMICS_FILTERS, ...RISK_FILTERS, ...DISCIPLINE_FILTERS })) {
      setEntryStateValue(location.key, name, value);
    }
    setFiltersEpoch((n) => n + 1);
  }

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
        <button className={tab === "practice" ? "active" : ""} onClick={() => setTab("practice")}>
          Практика
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
        {tab !== "practice" && (
          <button className="link-btn" onClick={handleExport}>
            Экспорт в Excel ({formatDateRu(exportDateFrom)}–{formatDateRu(exportDateTo)})
          </button>
        )}
      </div>

      {exportError && <div className="error-text">{exportError}</div>}
      {error && <div className="error-text">{error}</div>}

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
      {tab === "day" && <DayTab key={filtersEpoch} date={date} deptQuery={deptQuery} reloadKey={reloadKey} isStaff={isStaff} />}

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
        <DynamicsTab key={filtersEpoch} dateFrom={dateFrom} dateTo={dateTo} deptQuery={deptQuery} reloadKey={reloadKey} />
      )}

      {tab === "risk" && <RiskTab key={filtersEpoch} date={date} deptQuery={deptQuery} reloadKey={reloadKey} />}

      {tab === "practice" && <PracticeTab key={filtersEpoch} deptQuery={deptQuery} reloadKey={reloadKey} />}

      {tab === "discipline" && (
        <DisciplineTab key={filtersEpoch} dateFrom={dateFrom} dateTo={dateTo} deptQuery={deptQuery} reloadKey={reloadKey} isDeptHead={isDeptHead} />
      )}

      {tab === "vacant" && <VacantTab vacantGroups={vacantGroups} onAssign={setAssigningGroupId} />}

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
