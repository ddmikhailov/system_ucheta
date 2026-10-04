import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import QuickNoteModal from "../components/QuickNoteModal";
import { formatDateRu } from "../utils/date";
import { plural } from "../utils/plural";
import type { MyDay, MyDayAttention, MyDayTask } from "../api/types";

const DAYS: [string, string, string] = ["день", "дня", "дней"];

function headline(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const text = new Date(y, m - 1, d).toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function taskNote(t: MyDayTask): string {
  if (t.kind === "overdue") {
    const late = -t.days_left;
    return `просрочено на ${late} ${plural(late, DAYS)}${t.status === "returned" ? ", возвращено на доработку" : ""}`;
  }
  if (t.kind === "returned") return "возвращено на доработку";
  if (t.days_left === 0) return "срок — сегодня";
  return `осталось ${t.days_left} ${plural(t.days_left, DAYS)}`;
}

function attentionReasons(s: MyDayAttention, noWorkDays: number): string[] {
  const reasons: string[] = [];
  if (s.needs_work) reasons.push(`${s.risk_streak} пропусков подряд, записей за ${noWorkDays} дн. нет`);
  if (s.follow_up_overdue && s.follow_up_on) reasons.push(`вернуться к вопросу было до ${formatDateRu(s.follow_up_on)}`);
  if (s.follow_up_today) reasons.push("вернуться к вопросу сегодня");
  return reasons;
}

/** Стартовая страница куратора: что требует внимания сегодня. Собирается из уже имеющихся данных
 * (посещаемость, задачи, индивидуальная работа, досье). */
export default function MyDayPage() {
  const [data, setData] = useState<MyDay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<MyDayAttention | null>(null);

  const load = useCallback(() => {
    api
      .get<MyDay>("/my-day")
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить сводку"));
  }, []);

  useEffect(load, [load]);

  if (error && !data) return <div className="error-text">{error}</div>;
  if (!data) return <p className="hint">Загрузка…</p>;

  const pending = data.groups.filter((g) => g.today_status === "pending");
  const withMissed = data.groups.filter((g) => g.missed_total > 0);
  const nothingToDo =
    pending.length === 0 && withMissed.length === 0 && data.tasks.length === 0 && data.attention.length === 0;
  const waiting = data.review_waiting?.count ?? 0;

  return (
    <div className="my-day">
      <h2>Мой день</h2>
      <p className="hint">{headline(data.today)}</p>
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice}{" "}
          <button className="link-btn" onClick={() => setNotice(null)}>
            Скрыть
          </button>
        </div>
      )}

      {!data.leads_groups && waiting === 0 && <p className="hint">У вас нет закреплённых групп.</p>}

      {waiting > 0 && (
        <section className="my-day__section">
          <h3>На проверке</h3>
          <p>
            <Link to="/tasks" className="link-btn">
              Ждут вашего решения: {waiting}
            </Link>
          </p>
        </section>
      )}

      {data.leads_groups && (
        <>
          {nothingToDo && <p className="day-status submitted">На сегодня всё в порядке: срочного нет.</p>}

          <section className="my-day__section">
            <h3>Посещаемость</h3>
            <ul className="my-day__list">
              {data.groups.map((g) => (
                <li key={g.id} className="my-day__item">
                  <div>
                    <Link to={`/cabinet?group=${g.id}`} className="link-btn">
                      {g.code}
                    </Link>{" "}
                    <span className="hint">курс {g.course}</span>
                  </div>
                  <div>
                    {g.today_status === "submitted" && <span className="locked-badge">день сдан</span>}
                    {g.today_status === "pending" && <span className="risk-badge">день не сдан</span>}
                    {g.today_status === "no_study_day" && <span className="hint">сегодня занятий нет</span>}
                  </div>
                  {g.missed_total > 0 && (
                    <div className="my-day__missed">
                      Не сданы: {g.missed_total} {plural(g.missed_total, DAYS)}:
                      <span className="my-day__dates">
                        {g.missed_dates.map((d) => (
                          <Link key={d} to={`/cabinet?group=${g.id}&date=${d}`} className="link-btn">
                            {formatDateRu(d).slice(0, 5)}
                          </Link>
                        ))}
                        {g.missed_total > g.missed_dates.length && <span>и ранее</span>}
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>

          {data.tasks.length > 0 && (
            <section className="my-day__section">
              <h3>Задачи</h3>
              <ul className="my-day__list">
                {data.tasks.map((t) => (
                  <li key={t.assignment_id} className="my-day__item">
                    <div>
                      <Link to={`/tasks/assignment/${t.assignment_id}`} className="link-btn">
                        {t.title}
                      </Link>{" "}
                      <span className="hint">{t.group_code}</span>
                    </div>
                    <div className={t.kind === "due_soon" ? undefined : "error-text"}>
                      {taskNote(t)} (до {formatDateRu(t.due_date)})
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {data.attention.length > 0 && (
            <section className="my-day__section">
              <h3>Требуют внимания</h3>
              <ul className="my-day__list">
                {data.attention.map((s) => (
                  <li key={s.student_id} className="my-day__item">
                    <div>
                      <Link to={`/students/${s.student_id}`} className="link-btn">
                        {s.full_name}
                      </Link>{" "}
                      <span className="hint">{s.group_code}</span>
                    </div>
                    <div>{attentionReasons(s, data.no_work_days).join("; ")}</div>
                    <div>
                      <button onClick={() => setNoteFor(s)} aria-label={`Записать: ${s.full_name}`}>
                        Записать
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              {data.attention_total > data.attention.length && (
                <p className="hint">
                  Показаны первые {data.attention.length} из {data.attention_total}. Полный список — в разделе «Индивидуальная
                  работа».
                </p>
              )}
            </section>
          )}

          {data.birthdays.length > 0 && (
            <section className="my-day__section">
              <h3>Дни рождения</h3>
              <ul className="my-day__list">
                {data.birthdays.map((b) => (
                  <li key={b.student_id} className="my-day__item">
                    <div>
                      <Link to={`/students/${b.student_id}`} className="link-btn">
                        {b.full_name}
                      </Link>{" "}
                      <span className="hint">{b.group_code}</span>
                    </div>
                    <div>
                      {b.days_until === 0 ? <b>сегодня</b> : `${formatDateRu(b.date).slice(0, 5)} (через ${b.days_until} ${plural(b.days_until, DAYS)})`}
                      {" — "}исполняется {b.turns}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {noteFor && (
        <QuickNoteModal
          studentId={noteFor.student_id}
          studentName={noteFor.full_name}
          onClose={() => setNoteFor(null)}
          onSaved={() => {
            setNoteFor(null);
            setNotice(`Запись сохранена: ${noteFor.full_name}.`);
            load();
          }}
        />
      )}
    </div>
  );
}
