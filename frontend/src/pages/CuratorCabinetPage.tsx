import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { GroupSummary } from "../api/types";
import { plural } from "../utils/plural";

const STUDENTS: [string, string, string] = ["студент", "студента", "студентов"];

/** «Мои группы» (интерфейс 3.2): карточки групп куратора. Всё, что относится к группе — журнал, список
 * студентов, индивидуальная работа, соц. паспорт, план и отчёт, — открывается на странице группы.
 * Старые ссылки вида /cabinet?group=…&date=… (уведомления) ведут сразу в журнал этой группы. */
export default function CuratorCabinetPage() {
  const [searchParams] = useSearchParams();
  const [groups, setGroups] = useState<GroupSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const deepGroup = searchParams.get("group");

  useEffect(() => {
    if (deepGroup) return;
    api
      .get<GroupSummary[]>("/curator/groups")
      .then((gs) => setGroups(Array.isArray(gs) ? gs : []))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить список групп"));
  }, [deepGroup]);

  if (deepGroup) {
    const date = searchParams.get("date");
    return <Navigate to={`/cabinet/groups/${deepGroup}${date ? `?date=${date}` : ""}`} replace />;
  }
  if (error) return <div className="error-text">{error}</div>;
  if (groups === null) return <p className="hint">Загрузка…</p>;
  if (groups.length === 0) return <p>У вас нет закреплённых групп.</p>;
  // Одна группа — карточка ни к чему, сразу её страница.
  if (groups.length === 1) return <Navigate to={`/cabinet/groups/${groups[0].id}`} replace />;

  return (
    <div className="group-cards">
      {groups.map((g) => (
        <Link key={g.id} to={`/cabinet/groups/${g.id}`} className="group-card">
          <span className="group-card__code">{g.code}</span>
          <span className="group-card__meta">
            {g.course} курс · {g.role_type === "deputy" ? "заместитель куратора" : "куратор"}
          </span>
          <span className="group-card__stats">
            <span>
              {g.students_count} {plural(g.students_count, STUDENTS)}
            </span>
            {g.risk_count > 0 && <span className="group-card__risk">в группе риска: {g.risk_count}</span>}
          </span>
          <span className={`group-card__today ${g.is_submitted_today ? "is-ok" : "is-pending"}`}>
            {g.is_submitted_today ? "Сегодня сдано" : "Сегодня не сдано"}
          </span>
        </Link>
      ))}
    </div>
  );
}
