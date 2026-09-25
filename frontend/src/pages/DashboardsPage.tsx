import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { downloadFile } from "../api/client";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AssignCuratorModal from "../components/AssignCuratorModal";
import { useEscapeKey } from "../hooks/useEscapeKey";
import type {
  CuratorDisciplineRow,
  DayOverviewRow,
  DepartmentAdmin,
  DynamicsPoint,
  RiskStudentRow,
  StudentCard,
  StudyGroupAdmin,
  UserAdmin,
} from "../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

// Даты в API приходят в ISO (YYYY-MM-DD) — на экране показываем в привычном
// для колледжа виде ДД.ММ.ГГГГ (см. TODO.md 4).
function formatDateRu(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

type Tab = "day" | "dynamics" | "risk" | "discipline" | "vacant";

export default function DashboardsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isDeptHead = user?.role === "dept_head";
  // Админ/тьютор/учебный отдел видят весь колледж и могут сузить экспорт до
  // одного отделения; зав. отделением и так видит только своё (см. TODO.md 4).
  const canFilterDepartment = user?.role === "admin" || user?.role === "tutor" || user?.role === "edu_department";

  const [tab, setTab] = useState<Tab>("day");
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
  const [openStudentId, setOpenStudentId] = useState<number | null>(null);

  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [assigningGroupId, setAssigningGroupId] = useState<number | null>(null);
  const vacantGroups = useMemo(() => groups.filter((g) => g.is_active && !g.curator_name), [groups]);

  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [exportDepartmentId, setExportDepartmentId] = useState<number | "all">("all");
  const [exportError, setExportError] = useState<string | null>(null);

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
      .then((us) => setCurators(us.filter((u) => u.is_active && (u.role === "curator" || u.role === "deputy_curator"))))
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
  const exportDateFrom = tab === "day" || tab === "risk" ? date : dateFrom;
  const exportDateTo = tab === "day" || tab === "risk" ? date : dateTo;

  function handleExport() {
    setExportError(null);
    const deptParam = canFilterDepartment && exportDepartmentId !== "all" ? `&department_id=${exportDepartmentId}` : "";
    downloadFile(
      `/export/excel?date_from=${exportDateFrom}&date_to=${exportDateTo}${deptParam}`,
      `itog_${exportDateFrom}_${exportDateTo}.xlsx`,
    ).catch((err) => setExportError(err instanceof ApiError ? err.message : "Не удалось скачать файл"));
  }

  return (
    <div>
      <div className="tabs">
        <button className={tab === "day" ? "active" : ""} onClick={() => setTab("day")}>
          {isDeptHead ? "День по отделению" : "День по колледжу"}
        </button>
        <button className={tab === "dynamics" ? "active" : ""} onClick={() => setTab("dynamics")}>
          Динамика
        </button>
        <button className={tab === "risk" ? "active" : ""} onClick={() => setTab("risk")}>
          Группа риска
        </button>
        <button className={tab === "discipline" ? "active" : ""} onClick={() => setTab("discipline")}>
          Дисциплина кураторов
        </button>
        <button className={tab === "vacant" ? "active" : ""} onClick={() => setTab("vacant")}>
          Вакантные группы{vacantGroups.length > 0 ? ` (${vacantGroups.length})` : ""}
        </button>
        {canFilterDepartment && (
          <select
            value={exportDepartmentId}
            onChange={(e) => setExportDepartmentId(e.target.value === "all" ? "all" : Number(e.target.value))}
            title="Отделение для экспорта"
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
                onClick={() => navigate(`/admin?tab=journal&group=${r.study_group_id}&date=${date}`)}
                title="Открыть журнал группы на эту дату"
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
                  <button className="link-btn" onClick={() => setOpenStudentId(r.student_id)}>
                    {r.full_name}
                  </button>
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
              <tr key={r.study_group_id} className={r.missed > 0 ? "not-submitted-row" : ""}>
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
            Пока куратор не назначен, отмечать посещаемость в группе некому и напоминания никому не приходят —
            группа просто перечисляется в ежедневной сводке зав. отделением. Назначьте куратора или заместителя,
            чтобы группа заработала как обычно.
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

      {openStudentId !== null && (
        <StudentCardModal studentId={openStudentId} dateFrom={dateFrom} dateTo={dateTo} onClose={() => setOpenStudentId(null)} />
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

function StudentCardModal({
  studentId,
  dateFrom,
  dateTo,
  onClose,
}: {
  studentId: number;
  dateFrom: string;
  dateTo: string;
  onClose: () => void;
}) {
  const [card, setCard] = useState<StudentCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  useEffect(() => {
    api
      .get<StudentCard>(`/dashboards/students/${studentId}?date_from=${dateFrom}&date_to=${dateTo}`)
      .then(setCard)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка загрузки"));
  }, [studentId, dateFrom, dateTo]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Карточка студента" onClick={(e) => e.stopPropagation()}>
        {error && <div className="error-text">{error}</div>}
        {card && (
          <>
            <h3>{card.full_name}</h3>
            <p>
              Группа {card.group_code} · присутствие за период {formatDateRu(dateFrom)}–{formatDateRu(dateTo)}:{" "}
              {card.percent_period}%
            </p>
            <p className="hint">Период задаётся вкладкой «Динамика» — измените его там, если нужен другой диапазон.</p>
            <table className="dash-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Код</th>
                  <th>Основание</th>
                </tr>
              </thead>
              <tbody>
                {card.history.map((h, i) => (
                  <tr key={i}>
                    <td>{formatDateRu(h.date)}</td>
                    <td>{h.mark_name}</td>
                    <td>{h.basis_reference ?? "—"}</td>
                  </tr>
                ))}
                {card.history.length === 0 && (
                  <tr>
                    <td colSpan={3}>Пропусков за период нет.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}
        <div className="actions">
          <button onClick={onClose}>Закрыть</button>
        </div>
      </div>
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
