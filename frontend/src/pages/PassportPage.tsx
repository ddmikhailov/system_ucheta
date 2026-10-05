import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, downloadFile } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { COLLEGE_WIDE_ROLES, DOSSIER_AUDIT_ROLES, inRoles } from "../constants/roles";
import type { DepartmentAdmin } from "../api/types";

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

export default function PassportPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const groupId = searchParams.get("group");
  const [departmentId, setDepartmentId] = useState("");
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [passport, setPassport] = useState<GroupPassport | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!groupId) return;
    api
      .get<GroupPassport>(`/passport/group/${groupId}`)
      .then((p) => {
        setPassport(p);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить паспорт группы"));
  }, [groupId]);

  function exportExcel(path: string) {
    downloadFile(path, "social_passport.xlsx").catch((err) =>
      setError(err instanceof ApiError ? err.message : "Не удалось скачать файл")
    );
  }

  // Паспорт прошлой группы не показываем, пока грузится новый.
  const shown = passport && String(passport.group_id) === groupId ? passport : null;

  if (groupId) {
    return (
      <div>
        <p>
          <button className="link-btn" onClick={() => setSearchParams({})}>
            ← К сводке по группам
          </button>
        </p>
        {error && <div className="error-text">{error}</div>}
        {shown === null && !error && <p className="hint">Загрузка…</p>}
        {shown && <GroupView passport={shown} onExport={() => exportExcel(`/passport/export?group_id=${groupId}`)} />}
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
      {error && <div className="error-text">{error}</div>}
      {!summary && !error && <p className="hint">Загрузка…</p>}
      {summary && (
        <>
          {!summary.special_available && (
            <SpecialUnavailable technical={technical} />
          )}
          {summary.rows.length === 0 ? (
            <p className="hint">Нет доступных групп.</p>
          ) : (
            <div className="table-scroll"><table className="dash-table">
              <thead>
                <tr>
                  <th>Группа</th>
                  <th>Студентов</th>
                  <th>Несоверш.</th>
                  <th>Бюджет / договор</th>
                  <th>Без представителей</th>
                  <th>Досье пустое</th>
                  {summary.categories.map((c) => (
                    <th key={c.key}>{c.title}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...summary.rows, ...(summary.rows.length > 1 ? [summary.totals] : [])].map((r, i, all) => {
                  const isTotal = r.group_id === 0 && i === all.length - 1 && summary.rows.length > 1;
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

function GroupView({ passport: p, onExport }: { passport: GroupPassport; onExport: () => void }) {
  const { user } = useAuth();
  const technical = inRoles(user?.role, DOSSIER_AUDIT_ROLES);
  return (
    <div className="student-card">
      <div className="student-card__header">
        <h2>
          Социальный паспорт группы {p.group_code}
        </h2>
        <button className="link-btn" onClick={onExport}>
          Экспорт в Excel
        </button>
      </div>
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

      <h3 className="student-card__section">Особые категории</h3>
      {!p.special_available && (
        <SpecialUnavailable technical={technical} />
      )}
      <div className="table-scroll"><table className="dash-table">
        <thead>
          <tr>
            <th>Категория</th>
            <th>Человек</th>
            <th>Кто</th>
          </tr>
        </thead>
        <tbody>
          {p.categories.map((c) => (
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
