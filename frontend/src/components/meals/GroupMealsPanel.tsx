import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { GroupMeals, MealDay, MealSource, MealStudent, MealWeek } from "../../api/types";
import { formatDueShort, formatLocalDateTime } from "../../utils/date";
import { toast } from "../../utils/feedback";
import { filterByQuery } from "../../utils/searchMatch";
import { plural } from "../../utils/plural";
import { TabBar, TabPanel } from "../Tabs";

const SOURCE_TEXT: Record<MealSource, string> = {
  submitted: "подано",
  edited: "изменено",
  forecast: "прогноз",
};

type SubTab = "submit" | "days" | "students";
type EatsFilter = "all" | "yes" | "no";

/** Блок «Питание» группы — три подвкладки: «Подача» (число на неделю), «По дням» (правки до 10:00) и «Студенты»
 * (кто питается: «Да» / «Нет», как в «Моём ID»). `viewOnly` — просмотр для ответственной по питанию: без правок. */
export default function GroupMealsPanel({ groupId, viewOnly = false }: { groupId: number; viewOnly?: boolean }) {
  const [data, setData] = useState<GroupMeals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState<number[]>([]);
  const [sub, setSub] = useState<SubTab>("submit");
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

  const students = data?.students ?? [];
  const eaters = students.filter((s) => s.eats).length;
  const week: MealWeek | undefined = data?.weeks.find((w) => w.week_start === weekStart);
  // Итоговое число по умолчанию — столько, сколько отмечено питающимися (или уже подано), пока куратор не ввёл своё.
  const shownTotal = totalTouched ? total : String(week?.submitted_count ?? eaters);

  if (error) return <div className="error-text">{error}</div>;
  if (!data) return <p className="hint">Загрузка…</p>;

  const editable = data.can_edit && !viewOnly;
  const contract = data.funding === "contract";

  async function setEats(student: MealStudent, eats: boolean) {
    if (student.eats === eats) return;
    // Сразу показываем выбор, сохраняем в фоне; при ошибке возвращаем прежнее значение.
    setData((prev) => (prev ? { ...prev, students: prev.students.map((s) => (s.student_id === student.student_id ? { ...s, eats } : s)) } : prev));
    setSaving((ids) => [...ids, student.student_id]);
    setTotalTouched(false);
    try {
      await api.put(`/meals/groups/${groupId}/students/${student.student_id}`, { eats });
      await load();
    } catch (err) {
      setData((prev) => (prev ? { ...prev, students: prev.students.map((s) => (s.student_id === student.student_id ? { ...s, eats: student.eats } : s)) } : prev));
      toast(err instanceof ApiError ? err.message : "Не удалось сохранить", "error");
    } finally {
      setSaving((ids) => ids.filter((id) => id !== student.student_id));
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

  const weekHeader = (
    <>
      {data.weeks.length > 1 && (
        <div className="meals__weeks" role="group" aria-label="Неделя">
          {data.weeks.map((w, i) => (
            <button
              key={w.week_start}
              type="button"
              className={`chip-filter__item${w.week_start === week?.week_start ? " is-active" : ""}`}
              aria-pressed={w.week_start === week?.week_start}
              onClick={() => {
                setWeekStart(w.week_start);
                setTotalTouched(false);
              }}
            >
              {i === data.weeks.length - 1 ? "Следующая неделя" : "Эта неделя"} · с {formatDueShort(w.week_start)}
            </button>
          ))}
        </div>
      )}
      {week && <WeekStatus week={week} />}
    </>
  );

  return (
    <div className="meals">
      {contract && <div className="day-status weekend">Группа на договорной основе — питание не предоставляется.</div>}

      <TabBar
        tabs={[
          { key: "submit", label: "Подача" },
          { key: "days", label: "По дням" },
          { key: "students", label: "Студенты", badge: `${eaters}/${students.length}` },
        ]}
        active={sub}
        onChange={(key) => setSub(key as SubTab)}
        label="Разделы питания"
        idPrefix="meals"
        variant="sub"
      />

      <TabPanel idPrefix="meals" tabKey="submit" active={sub}>
        {contract || !week ? (
          <p className="hint">Подавать питание для этой группы не нужно.</p>
        ) : (
          <>
            {weekHeader}
            <div className="meals-cards">
              <div className="meals-card">
                <span className="meals-card__label">Отмечено питающихся</span>
                <span className="meals-card__value">{eaters}</span>
                <span className="meals-card__note">из {students.length} {plural(students.length, ["студента", "студентов", "студентов"])}</span>
              </div>
              <div className="meals-card">
                <label className="meals-card__label" htmlFor={`meals-total-${groupId}`}>Итоговое число на неделю</label>
                {editable ? (
                  <input
                    id={`meals-total-${groupId}`}
                    type="number"
                    inputMode="numeric"
                    min={0}
                    max={eaters}
                    value={shownTotal}
                    onChange={(e) => {
                      setTotal(e.target.value);
                      setTotalTouched(true);
                    }}
                    aria-label="Итоговое число питающихся на неделю"
                  />
                ) : (
                  <span className="meals-card__value">{week.submitted_count ?? "—"}</span>
                )}
                <span className="meals-card__note">не больше {eaters}</span>
              </div>
              {editable && (
                <div className="meals-card meals-card--action">
                  <button type="button" className="btn-primary" disabled={busy} onClick={submitWeek}>
                    {week.status === "submitted" ? "Подать заново" : "Подать питание"}
                  </button>
                  <span className="meals-card__note">Отдельный день можно поправить во вкладке «По дням»</span>
                </div>
              )}
            </div>

            <div className="meals-tip" role="note">
              {data.attendance_percent == null ? (
                <>Данных о посещаемости за прошлую неделю пока нет — советуем подать столько, сколько питающихся.</>
              ) : (
                <>
                  Средняя посещаемость группы за последнюю неделю — <b>{Math.round(data.attendance_percent)}%</b>. Советуем подать{" "}
                  <b>{data.hint}</b>
                  {data.hint !== eaters && <> из {eaters} питающихся</>}.
                </>
              )}
              {editable && data.attendance_percent != null && data.hint !== Number(shownTotal) && (
                <button
                  type="button"
                  className="btn-secondary meals-tip__apply"
                  onClick={() => {
                    setTotal(String(data.hint));
                    setTotalTouched(true);
                  }}
                >
                  Подставить {data.hint}
                </button>
              )}
            </div>
          </>
        )}
      </TabPanel>

      <TabPanel idPrefix="meals" tabKey="days" active={sub}>
        {contract || !week ? (
          <p className="hint">У этой группы нет питания.</p>
        ) : (
          <>
            {weekHeader}
            <div className="table-scroll">
              <table className="dash-table roster-table compact-cards meals__days">
                <thead>
                  <tr>
                    <th>День</th>
                    <th>Число</th>
                    <th>Источник</th>
                    <th>Правка до</th>
                    {editable && <th aria-label="Действия" />}
                  </tr>
                </thead>
                <tbody>
                  {week.days.map((day) => {
                    const input = dayInputs[day.date];
                    return (
                      <tr key={day.date} className={day.source === "forecast" ? "meals__row--forecast" : undefined}>
                        <td data-label="День">{formatDueShort(day.date)}</td>
                        <td data-label="Число">
                          {editable && day.open ? (
                            <input
                              type="number"
                              inputMode="numeric"
                              min={0}
                              max={eaters}
                              value={input ?? String(day.count)}
                              aria-label={`Число на ${day.date.split("-").reverse().join(".")}`}
                              onChange={(e) => setDayInputs((prev) => ({ ...prev, [day.date]: e.target.value }))}
                            />
                          ) : (
                            <b>{day.count}</b>
                          )}
                        </td>
                        <td data-label="Источник">
                          <span className={`meals-source meals-source--${day.source}`}>{SOURCE_TEXT[day.source]}</span>
                        </td>
                        <td data-label="Правка до">{day.open ? formatLocalDateTime(day.cutoff) : <span className="meals__closed">закрыто</span>}</td>
                        {editable && (
                          <td data-label="" className="meals__day-actions">
                            {day.open && (
                              <div className="meals__day-buttons">
                                <button
                                  type="button"
                                  className="btn-secondary"
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
                              </div>
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
            </div>
            <p className="hint">Число на день можно менять до 10:00 предыдущего учебного дня — потом оно закрывается для кухни.</p>
          </>
        )}
      </TabPanel>

      <TabPanel idPrefix="meals" tabKey="students" active={sub}>
        <StudentsList students={students} editable={editable} saving={saving} onChange={setEats} />
      </TabPanel>
    </div>
  );
}

/** Список группы: поиск, «Все / Питаются / Не питаются» и пара кнопок «Да» / «Нет» у каждого студента. */
function StudentsList({
  students, editable, saving, onChange,
}: {
  students: MealStudent[];
  editable: boolean;
  saving: number[];
  onChange: (student: MealStudent, eats: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<EatsFilter>("all");
  const eaters = students.filter((s) => s.eats).length;
  const locked = students.filter((s) => s.locked_reason).length;
  const visible = useMemo(() => {
    let list = students;
    if (filter === "yes") list = list.filter((s) => s.eats);
    if (filter === "no") list = list.filter((s) => !s.eats);
    return filterByQuery(list, query, (s) => s.full_name);
  }, [students, filter, query]);

  if (students.length === 0) return <p className="hint">В группе нет студентов.</p>;
  return (
    <div>
      <p className="meals-summary" aria-live="polite">
        <span>Питаются: <b>{eaters}</b> из {students.length}</span>
        <span>Не питаются: <b>{students.length - eaters}</b></span>
        {locked > 0 && <span>На договорной основе: <b>{locked}</b></span>}
      </p>
      <div className="toolbar toolbar--filters meals-filters">
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Найти студента" aria-label="Поиск студента" />
        <div className="chip-filter" role="group" aria-label="Показать">
          {([["all", "Все"], ["yes", "Питаются"], ["no", "Не питаются"]] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`chip-filter__item${filter === key ? " is-active" : ""}`}
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {editable && <p className="hint">Нажмите «Да» или «Нет» — выбор сохраняется сразу. Студенты на договорной основе не питаются, включить им питание нельзя.</p>}
      <div className="table-scroll">
        <table className="dash-table roster-table compact-cards meals-students">
          <thead>
            <tr>
              <th>№</th>
              <th>Студент</th>
              <th>Питается</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((s) => {
              const lockedRow = s.locked_reason != null;
              const off = !editable || lockedRow || saving.includes(s.student_id);
              return (
                <tr key={s.student_id} className={s.eats ? undefined : "meals-students__off"}>
                  <td data-label="№">{students.indexOf(s) + 1}</td>
                  <td data-label="Студент">{s.full_name}</td>
                  <td data-label="Питается" className="meals-students__cell">
                    <div className="meals-students__body">
                      <div className="yesno" role="group" aria-label={`Питается: ${s.full_name}`}>
                        <button
                          type="button"
                          className={`yesno__btn yesno__btn--yes${s.eats ? " is-active" : ""}`}
                          aria-pressed={s.eats}
                          disabled={off}
                          onClick={() => onChange(s, true)}
                        >
                          Да
                        </button>
                        <button
                          type="button"
                          className={`yesno__btn yesno__btn--no${!s.eats ? " is-active" : ""}`}
                          aria-pressed={!s.eats}
                          disabled={off}
                          onClick={() => onChange(s, false)}
                        >
                          Нет
                        </button>
                      </div>
                      {s.locked_reason && <span className="hint">{s.locked_reason}</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={3}>Под выбранные условия никто не подошёл.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function WeekStatus({ week }: { week: MealWeek }) {
  if (week.status === "submitted") {
    return (
      <div className="day-status submitted">
        Подано: <b>{week.submitted_count}</b>
        {week.submitted_at ? ` · ${formatLocalDateTime(week.submitted_at)}` : ""}. Отдельный день можно поправить до 10:00 предыдущего учебного дня.
      </div>
    );
  }
  if (week.status === "pending") {
    return (
      <div className="day-status not-submitted">
        Подайте питание до <b>{formatLocalDateTime(week.deadline)}</b>. Если не подать, в свод пойдёт прогноз ({week.forecast}).
      </div>
    );
  }
  return (
    <div className="day-status not-submitted">
      Срок подачи прошёл ({formatLocalDateTime(week.deadline)}), в свод идёт прогноз ({week.forecast}). Подать питание можно, пока открыты дни недели.
    </div>
  );
}
