import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { GroupMeals, MealDay, MealSource, MealWeek } from "../../api/types";
import { formatDateRu, formatDueShort, formatLocalDateTime } from "../../utils/date";
import { toast } from "../../utils/feedback";

const SOURCE_TEXT: Record<MealSource, string> = {
  submitted: "подано",
  edited: "изменено",
  forecast: "прогноз",
};

/** Вкладка «Питание» группы: кто питается, подача на неделю и правки по дням.
 * `viewOnly` — просмотр для ответственной по питанию и свода: те же списки, но без кнопок. */
export default function GroupMealsPanel({ groupId, viewOnly = false }: { groupId: number; viewOnly?: boolean }) {
  const [data, setData] = useState<GroupMeals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [weekStart, setWeekStart] = useState<string | null>(null);
  const [total, setTotal] = useState("");
  const [totalTouched, setTotalTouched] = useState(false);
  const [dayInputs, setDayInputs] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const fresh = await api.get<GroupMeals>(`/meals/groups/${groupId}`);
      setData(fresh);
      setError(null);
      setWeekStart((current) => current ?? fresh.weeks[fresh.weeks.length - 1]?.week_start ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить питание");
    }
  }, [groupId]);

  useEffect(() => {
    // Загрузка при открытии вкладки: setState — после await внутри load().
    // oxlint-disable-next-line react/set-state-in-effect
    load();
  }, [load]);

  const week: MealWeek | undefined = data?.weeks.find((w) => w.week_start === weekStart);
  const eaters = data?.eaters ?? 0;
  // Итоговое число по умолчанию — столько, сколько отмечено питающимися (или уже подано), пока куратор не ввёл своё.
  const shownTotal = totalTouched ? total : String(week?.submitted_count ?? eaters);

  if (error) return <div className="error-text">{error}</div>;
  if (!data) return <p className="hint">Загрузка…</p>;

  const editable = data.can_edit && !viewOnly;
  const contract = data.funding === "contract";

  async function toggleStudent(studentId: number, eats: boolean) {
    setBusy(true);
    try {
      await api.put(`/meals/groups/${groupId}/students/${studentId}`, { eats });
      setTotalTouched(false);
      await load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Не удалось сохранить", "error");
    } finally {
      setBusy(false);
    }
  }

  function applyWeek(updated: MealWeek) {
    setData((prev) => (prev ? { ...prev, weeks: prev.weeks.map((w) => (w.week_start === updated.week_start ? updated : w)) } : prev));
  }

  async function submitWeek() {
    if (!week) return;
    const count = Number(shownTotal);
    if (!Number.isInteger(count) || count < 0) {
      toast("Введите число питающихся целым числом", "error");
      return;
    }
    setBusy(true);
    try {
      applyWeek(await api.post<MealWeek>(`/meals/groups/${groupId}/week`, { week_start: week.week_start, count }));
      toast("Питание подано");
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Не удалось подать питание", "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveDay(day: MealDay, count: number | null) {
    setBusy(true);
    try {
      applyWeek(await api.put<MealWeek>(`/meals/groups/${groupId}/day`, { date: day.date, count }));
      setDayInputs((prev) => {
        const next = { ...prev };
        delete next[day.date];
        return next;
      });
      toast(count === null ? "Число на день возвращено к недельному" : "Число на день сохранено");
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Не удалось сохранить", "error");
    } finally {
      setBusy(false);
    }
  }

  const students = data.students;
  return (
    <div className="meals">
      {contract && (
        <div className="day-status weekend">Группа на договорной основе — питание не предоставляется.</div>
      )}

      {!contract && week && (
        <section className="meals__week" aria-label="Подача питания">
          {data.weeks.length > 1 && (
            <div className="meals__weeks" role="group" aria-label="Неделя">
              {data.weeks.map((w, i) => (
                <button
                  key={w.week_start}
                  type="button"
                  className={w.week_start === week.week_start ? "btn-primary" : "btn-secondary"}
                  aria-pressed={w.week_start === week.week_start}
                  onClick={() => {
                    setWeekStart(w.week_start);
                    setTotalTouched(false);
                  }}
                >
                  {i === data.weeks.length - 1 ? "Следующая неделя" : "Эта неделя"} · {formatDueShort(w.week_start)}
                </button>
              ))}
            </div>
          )}

          <WeekStatus week={week} />

          <div className="meals__counts">
            <div className="meals__count">
              <span className="meals__count-value">{eaters}</span>
              <span className="meals__count-label">отмечено питающихся</span>
            </div>
            {editable ? (
              <label className="meals__total">
                Итоговое число на неделю
                <input
                  type="number"
                  min={0}
                  max={eaters}
                  value={shownTotal}
                  onChange={(e) => {
                    setTotal(e.target.value);
                    setTotalTouched(true);
                  }}
                  aria-label="Итоговое число питающихся на неделю"
                />
              </label>
            ) : (
              week.submitted_count != null && (
                <div className="meals__count">
                  <span className="meals__count-value">{week.submitted_count}</span>
                  <span className="meals__count-label">подано на неделю</span>
                </div>
              )
            )}
            {editable && (
              <button type="button" className="btn-primary" disabled={busy} onClick={submitWeek}>
                {week.status === "submitted" ? "Подать заново" : "Подать питание"}
              </button>
            )}
          </div>

          <p className="hint meals__hint">
            {data.attendance_percent == null
              ? "Данных о посещаемости за прошлую неделю пока нет — советуем подать столько, сколько питающихся."
              : `Средняя посещаемость группы за последнюю неделю — ${Math.round(data.attendance_percent)}%. Советуем подать ${data.hint} ${data.hint === eaters ? "" : `из ${eaters} питающихся`}`.trim() + "."}
            {editable && data.hint !== Number(shownTotal) && data.attendance_percent != null && (
              <>
                {" "}
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => {
                    setTotal(String(data.hint));
                    setTotalTouched(true);
                  }}
                >
                  Подставить {data.hint}
                </button>
              </>
            )}
          </p>

          <table className="dash-table meals__days">
            <thead>
              <tr>
                <th>День</th>
                <th>Число</th>
                <th>Источник</th>
                <th>Правка до</th>
                {editable && <th />}
              </tr>
            </thead>
            <tbody>
              {week.days.map((day) => {
                const input = dayInputs[day.date];
                return (
                  <tr key={day.date} className={day.source === "forecast" ? "meals__row--forecast" : undefined}>
                    <td>{formatDueShort(day.date)}</td>
                    <td>
                      {editable && day.open ? (
                        <input
                          type="number"
                          min={0}
                          max={eaters}
                          value={input ?? String(day.count)}
                          aria-label={`Число на ${formatDateRu(day.date)}`}
                          onChange={(e) => setDayInputs((prev) => ({ ...prev, [day.date]: e.target.value }))}
                        />
                      ) : (
                        day.count
                      )}
                    </td>
                    <td>{SOURCE_TEXT[day.source]}</td>
                    <td>{day.open ? formatLocalDateTime(day.cutoff) : "закрыто"}</td>
                    {editable && (
                      <td className="meals__day-actions">
                        {day.open && (
                          <>
                            <button
                              type="button"
                              className="link-btn"
                              disabled={busy || input === undefined || Number(input) === day.count}
                              onClick={() => saveDay(day, Number(input))}
                            >
                              Сохранить
                            </button>
                            {day.source === "edited" && (
                              <button type="button" className="link-btn" disabled={busy} onClick={() => saveDay(day, null)}>
                                Сбросить
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
              {week.days.length === 0 && (
                <tr>
                  <td colSpan={editable ? 5 : 4}>На этой неделе у группы нет учебных дней.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      <section className="meals__students" aria-label="Кто питается">
        <h3>
          Кто питается <span className="hint">{eaters} из {students.length}</span>
        </h3>
        {students.length === 0 ? (
          <p className="hint">В группе нет студентов.</p>
        ) : (
          <ul className="meals__list">
            {students.map((s) => (
              <li key={s.student_id} className={s.eats ? "meals__student" : "meals__student meals__student--off"}>
                <label title={s.locked_reason ?? undefined}>
                  <input
                    type="checkbox"
                    checked={s.eats}
                    disabled={!editable || busy || s.locked_reason != null}
                    onChange={(e) => toggleStudent(s.student_id, e.target.checked)}
                    aria-label={`Питается: ${s.full_name}`}
                  />{" "}
                  {s.full_name}
                </label>
                {s.locked_reason && <span className="hint"> · {s.locked_reason}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function WeekStatus({ week }: { week: MealWeek }) {
  if (week.status === "submitted") {
    return (
      <div className="day-status submitted">
        Подано: {week.submitted_count}
        {week.submitted_at ? ` · ${formatLocalDateTime(week.submitted_at)}` : ""}. Отдельный день можно поправить до 10:00 предыдущего учебного дня.
      </div>
    );
  }
  if (week.status === "pending") {
    return (
      <div className="day-status not-submitted">
        Подайте питание до {formatLocalDateTime(week.deadline)}. Если не подать, в свод пойдёт прогноз ({week.forecast}).
      </div>
    );
  }
  return (
    <div className="day-status not-submitted">
      Срок подачи прошёл ({formatLocalDateTime(week.deadline)}), в свод идёт прогноз ({week.forecast}). Подать питание можно, пока открыты дни недели.
    </div>
  );
}
