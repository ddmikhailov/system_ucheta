import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import GroupRhythm from "../components/GroupRhythm";
import QuickNoteModal from "../components/QuickNoteModal";
import StatusMark from "../components/StatusMark";
import { formatDateRu, formatDayMonthRu, formatWeekdayLong } from "../utils/date";
import { toast } from "../utils/feedback";
import { initials } from "../utils/taskAnswers";
import { plural } from "../utils/plural";
import type { MarkKind } from "../utils/statusMark";
import type { MyDay, MyDayAttention, MyDayTask } from "../api/types";

const DAYS: [string, string, string] = ["день", "дня", "дней"];
const THINGS: [string, string, string] = ["дело", "дела", "дел"];

function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Доброе утро";
  if (hour >= 12 && hour < 17) return "Добрый день";
  if (hour >= 17 && hour < 23) return "Добрый вечер";
  return "Доброй ночи";
}

/** «Иванова Анна Ивановна» → «Анна Ивановна»: так к куратору обращаются в колледже. */
function addressName(fullName: string | undefined): string {
  const parts = (fullName ?? "").trim().split(/\s+/).filter(Boolean);
  return parts.length >= 2 ? parts.slice(1).join(" ") : (parts[0] ?? "");
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

function taskMark(t: MyDayTask): MarkKind {
  if (t.kind === "overdue") return "overdue";
  if (t.kind === "returned") return "returned";
  return t.status === "in_progress" ? "in_progress" : "new";
}

function attentionReasons(s: MyDayAttention, noWorkDays: number): string[] {
  const reasons: string[] = [];
  if (s.needs_work) reasons.push(`${s.risk_streak} пропусков подряд, записей за ${noWorkDays} дн. нет`);
  if (s.follow_up_overdue && s.follow_up_on) reasons.push(`вернуться к вопросу было до ${formatDateRu(s.follow_up_on)}`);
  if (s.follow_up_today) reasons.push("вернуться к вопросу сегодня");
  return reasons;
}

/** Стартовая страница куратора: что требует внимания сегодня — одним списком дел с понятным концом.
 * Собирается из уже имеющихся данных (посещаемость, задачи, индивидуальная работа, досье). */
export default function MyDayPage() {
  const { user } = useAuth();
  const [data, setData] = useState<MyDay | null>(null);
  const [error, setError] = useState<string | null>(null);
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
  const things = pending.length + data.tasks.length + data.attention.length;
  const nothingToDo = things === 0 && withMissed.length === 0;
  const waiting = data.review_waiting?.count ?? 0;
  const name = addressName(user?.full_name);

  return (
    <div className="my-day">
      <header className="my-day__hello">
        <p className="my-day__date">{formatWeekdayLong(data.today)}</p>
        <h2>
          {greeting(new Date().getHours())}
          {name ? `, ${name}` : ""}
        </h2>
        {data.leads_groups && (
          <p className="my-day__summary">
            {things > 0 ? `${things} ${plural(things, THINGS)} на сегодня` : "Срочных дел нет"}
            {data.birthdays.some((b) => b.days_until === 0) && ", сегодня есть день рождения"}
          </p>
        )}
      </header>
      {error && <div className="error-text">{error}</div>}

      {pending.length > 0 && (
        <div className="my-day__cta">
          {pending.map((g) => (
            <Link key={g.id} to={`/cabinet?group=${g.id}`} className="big-cta">
              Отметить посещаемость {g.code}
            </Link>
          ))}
        </div>
      )}

      {!data.leads_groups && waiting === 0 && <p className="empty-state">У вас нет закреплённых групп.</p>}

      {waiting > 0 && (
        <section className="my-day__section" aria-label="На проверке">
          <h3>На проверке</h3>
          <div className="my-day__card">
            <Link to="/tasks" className="link-btn">
              Ждут вашего решения: {waiting}
            </Link>
          </div>
        </section>
      )}

      {data.leads_groups && nothingToDo && (
        <div className="done-state" role="status">
          <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
            <circle cx="12" cy="12" r="11" className="done-state__circle" />
            <path d="M7 12.5l3.2 3.2L17 9" className="done-state__check" />
          </svg>
          <span>На сегодня всё в порядке: срочного нет.</span>
        </div>
      )}

      {(data.tasks.length > 0 || data.attention.length > 0) && (
        <section className="my-day__section" aria-label="Сделать сегодня">
          <h3>Сделать сегодня</h3>
          <ul className="todo-list">
            {data.tasks.map((t) => (
              <li key={`t-${t.assignment_id}`} className="todo-item">
                <StatusMark kind={taskMark(t)} />
                <div className="todo-item__main">
                  <Link to={`/tasks/assignment/${t.assignment_id}`} className="todo-item__title">
                    {t.title}
                  </Link>
                  <div className={`todo-item__note${t.kind === "due_soon" ? "" : " is-hot"}`}>
                    <span className="group-chip">{t.group_code}</span> {taskNote(t)} (до {formatDateRu(t.due_date)})
                  </div>
                </div>
              </li>
            ))}
            {data.attention.map((s) => (
              <li key={`s-${s.student_id}`} className="todo-item">
                <span className="avatar" aria-hidden="true">
                  {initials(s.full_name)}
                </span>
                <div className="todo-item__main">
                  <Link to={`/students/${s.student_id}`} className="todo-item__title">
                    {s.full_name}
                  </Link>
                  <div className="todo-item__note">
                    <span className="group-chip">{s.group_code}</span>{" "}
                    {attentionReasons(s, data.no_work_days).map((r) => (
                      <span key={r} className="todo-item__reason">
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
                <button className="btn-secondary" onClick={() => setNoteFor(s)} aria-label={`Записать: ${s.full_name}`}>
                  Записать
                </button>
              </li>
            ))}
          </ul>
          {data.attention_total > data.attention.length && (
            <p className="hint">
              Показаны первые {data.attention.length} из {data.attention_total}. Полный список — в разделе «Индивидуальная работа».
            </p>
          )}
        </section>
      )}

      {data.leads_groups && (
        <section className="my-day__section" aria-label="Группы">
          <h3>Группы</h3>
          <div className="group-cards">
            {data.groups.map((g) => (
              <article key={g.id} className="group-card">
                <div className="group-card__head">
                  <Link to={`/cabinet?group=${g.id}`} className="group-card__code">
                    {g.code}
                  </Link>
                  <span className="hint">курс {g.course}</span>
                  <span className="group-card__today">
                    {g.today_status === "submitted" && <span className="locked-badge">день сдан</span>}
                    {g.today_status === "pending" && <span className="risk-badge">день не сдан</span>}
                    {g.today_status === "no_study_day" && <span className="hint">сегодня занятий нет</span>}
                  </span>
                </div>
                {g.rhythm && <GroupRhythm days={g.rhythm} />}
                {g.missed_total > 0 && (
                  <div className="my-day__missed">
                    Не сданы {g.missed_total} {plural(g.missed_total, DAYS)}:
                    <span className="my-day__dates">
                      {g.missed_dates.map((d) => (
                        <Link key={d} to={`/cabinet?group=${g.id}&date=${d}`} className="link-btn">
                          {formatDayMonthRu(d)}
                        </Link>
                      ))}
                      {g.missed_total > g.missed_dates.length && <span>и ранее</span>}
                    </span>
                  </div>
                )}
              </article>
            ))}
          </div>
          {data.groups.some((g) => g.rhythm?.length) && (
            <p className="rhythm-legend hint">
              {(
                [
                  ["ok", "без пропусков без причины"],
                  ["absent", "пропуски без причины"],
                  ["missing", "день не сдан"],
                  ["off", "занятий нет"],
                ] as const
              ).map(([kind, text]) => (
                <span key={kind} className="rhythm-legend__item">
                  <i className={`rhythm__day rhythm__day--${kind}`} aria-hidden="true" />
                  {text}
                </span>
              ))}
            </p>
          )}
        </section>
      )}

      {data.birthdays.length > 0 && (
        <section className="my-day__section" aria-label="Дни рождения">
          <h3>Дни рождения</h3>
          <ul className="todo-list">
            {data.birthdays.map((b) => (
              <li key={b.student_id} className="todo-item">
                <span className="avatar" aria-hidden="true">
                  {initials(b.full_name)}
                </span>
                <div className="todo-item__main">
                  <Link to={`/students/${b.student_id}`} className="todo-item__title">
                    {b.full_name}
                  </Link>
                  <div className="todo-item__note">
                    <span className="group-chip">{b.group_code}</span>{" "}
                    {b.days_until === 0 ? <b>сегодня</b> : `${formatDayMonthRu(b.date)} (через ${b.days_until} ${plural(b.days_until, DAYS)})`}
                    {" — "}исполняется {b.turns}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {noteFor && (
        <QuickNoteModal
          studentId={noteFor.student_id}
          studentName={noteFor.full_name}
          onClose={() => setNoteFor(null)}
          onSaved={() => {
            setNoteFor(null);
            toast(`Запись сохранена: ${noteFor.full_name}.`);
            load();
          }}
        />
      )}
    </div>
  );
}
