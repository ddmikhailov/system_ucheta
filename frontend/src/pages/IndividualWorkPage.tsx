import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { formatDateRu } from "../utils/date";
import type { IndividualWorkGroup } from "../api/types";

interface GroupOption {
  id: number;
  code: string;
  course: number;
}

// Обзор индивидуальной работы по группе: кто в «группе внимания» (серия пропусков, уже ведётся работа),
// с кем давно не работали и где подошёл срок «вернуться к вопросу». Записи делаются в карточке студента.
export default function IndividualWorkPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [groups, setGroups] = useState<GroupOption[] | null>(null);
  const [data, setData] = useState<IndividualWorkGroup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const groupId = searchParams.get("group");

  useEffect(() => {
    api
      .get<GroupOption[]>("/individual-work/groups")
      .then((list) => {
        setGroups(list);
        if (!groupId && list.length > 0) setSearchParams({ group: String(list[0].id) }, { replace: true });
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить список групп");
        setGroups([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!groupId) return;
    let cancelled = false;
    api
      .get<IndividualWorkGroup>(`/individual-work/groups/${groupId}`)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Не удалось загрузить журнал");
      });
    return () => {
      cancelled = true;
    };
  }, [groupId]);

  if (groups === null) return <p className="hint">Загрузка…</p>;
  if (groups.length === 0) return <p>{error ?? "Нет доступных групп."}</p>;

  const current = data && String(data.group_id) === groupId ? data : null;

  return (
    <div>
      <div className="toolbar">
        <select value={groupId ?? ""} onChange={(e) => setSearchParams({ group: e.target.value })} aria-label="Группа">
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.code} (курс {g.course})
            </option>
          ))}
        </select>
      </div>
      <p className="hint">
        Здесь — студенты с серией неуважительных пропусков и те, с кем уже ведётся индивидуальная работа. Беседы, вызовы
        родителей, Совет профилактики и визиты записываются в карточке студента («Индивидуальная работа и заметки»).
      </p>
      {error && <div className="error-text">{error}</div>}
      {!current ? (
        !error && <p className="hint">Загрузка…</p>
      ) : current.rows.length === 0 ? (
        <p className="hint">В группе {current.group_code} нет студентов с серией пропусков и записей об индивидуальной работе.</p>
      ) : (
        <table className="dash-table roster-table">
          <thead>
            <tr>
              <th>Студент</th>
              <th>Пропусков подряд</th>
              <th>Работа</th>
              <th>Вернуться к вопросу</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {current.rows.map((r) => (
              <tr key={r.student_id} className={r.needs_attention ? "risk-row" : ""}>
                <td data-label="Студент">
                  <Link to={`/students/${r.student_id}`} className="link-btn">
                    {r.full_name}
                  </Link>
                </td>
                <td data-label="Пропусков подряд">{r.is_risk ? r.risk_streak : "—"}</td>
                <td data-label="Работа">
                  {r.work_count > 0 ? `${r.work_count} зап., последняя ${formatDateRu(r.last_work_on!)}` : "не велась"}
                </td>
                <td data-label="Вернуться к вопросу">
                  {r.next_follow_up_on ? (
                    <span className={r.follow_up_overdue ? "error-text" : undefined}>
                      {formatDateRu(r.next_follow_up_on)}
                      {r.follow_up_overdue && " (просрочено)"}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td data-label="Статус">
                  {r.needs_attention ? (
                    <span className="risk-badge">нужна работа: нет записей за {current.no_work_days} дн.</span>
                  ) : r.is_risk ? (
                    "работа ведётся"
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
