import { useState } from "react";
import type { MonthDayStatus } from "../../api/types";
import { addDaysIso, formatMonthTitle, formatWeekdayLong, toIso } from "../../utils/date";

const NON_WORKING = ["weekend", "holiday", "vacation"];
const WEEKDAY_HEADERS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

type DayState = "ok" | "late" | "missing" | "off" | "future" | "planned";

const STATE_TEXT: Record<DayState, string> = {
  ok: "сдано вовремя",
  late: "сдано задним числом",
  missing: "не сдано",
  off: "нерабочий день",
  future: "ещё не наступил — можно запланировать отметки",
  planned: "ещё не наступил, отметки запланированы",
};

function dayState(status: MonthDayStatus | undefined, iso: string, today: string): DayState {
  if (status && NON_WORKING.includes(status.day_type)) return "off";
  if (iso > today) return (status?.marks_count ?? 0) > 0 ? "planned" : "future";
  if (!status) return "missing";
  if (status.is_submitted) return status.is_on_time ? "ok" : "late";
  return "missing";
}

/** Навигация по дням журнала: «‹ предыдущий учебный день», дата с днём недели, «следующий ›»,
 * «Сегодня» и календарь месяца с числами и цветом сдачи. Месяц листается стрелками — так
 * открывается любой прошлый день, а не только сегодняшний. */
export default function DayNavigator({
  date,
  today,
  monthStatus,
  onChange,
}: {
  date: string;
  today: string;
  monthStatus: MonthDayStatus[];
  onChange: (date: string) => void;
}) {
  // На телефоне календарь свёрнут под кнопку — иначе итоги дня оказываются на втором экране.
  // На телефоне календарь свёрнут (экономим высоту), на широком экране открыт, как и раньше.
  const [calendarOpen, setCalendarOpen] = useState(
    () => typeof window.matchMedia === "function" && window.matchMedia("(min-width: 721px)").matches,
  );
  const byDate = new Map(monthStatus.map((d) => [d.date, d]));
  const isOff = (iso: string) => {
    const s = byDate.get(iso);
    return !!s && NON_WORKING.includes(s.day_type);
  };

  // Соседний учебный день: пропускаем известные нерабочие дни этого месяца (не дальше двух недель).
  function step(dir: -1 | 1): string {
    let next = addDaysIso(date, dir);
    for (let i = 0; i < 14 && isOff(next); i++) next = addDaysIso(next, dir);
    return next;
  }
  const nextDay = step(1);

  const [y, m] = date.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const daysInMonth = new Date(y, m, 0).getDate();
  const lead = (first.getDay() + 6) % 7; // понедельник — первый столбец
  const cells: (string | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => toIso(new Date(y, m - 1, i + 1))),
  ];
  const prevMonthLast = toIso(new Date(y, m - 1, 0));
  const nextMonthFirst = toIso(new Date(y, m, 1));

  return (
    <div className={`day-nav${calendarOpen ? " is-calendar-open" : ""}`}>
      <div className="day-nav__bar">
        <button type="button" className="day-nav__arrow" onClick={() => onChange(step(-1))} aria-label="Предыдущий учебный день">
          ‹
        </button>
        <div className="day-nav__current">
          <span className="day-nav__weekday">{formatWeekdayLong(date)}</span>
          <input
            type="date"
            aria-label="Дата"
            value={date}
            onChange={(e) => e.target.value && onChange(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="day-nav__arrow"
          onClick={() => onChange(nextDay)}
          aria-label="Следующий учебный день"
        >
          ›
        </button>
        <div className="day-nav__quick">
          <button type="button" className="btn-secondary" onClick={() => onChange(today)} disabled={date === today}>
            Сегодня
          </button>
          <button
            type="button"
            className="btn-secondary day-nav__cal-toggle"
            aria-expanded={calendarOpen}
            onClick={() => setCalendarOpen((v) => !v)}
          >
            {calendarOpen ? "Скрыть календарь" : "Календарь"}
          </button>
        </div>
      </div>

      <div className="month-cal" aria-label={`Календарь: ${formatMonthTitle(date)}`}>
        <div className="month-cal__head">
          <button type="button" className="day-nav__arrow day-nav__arrow--small" onClick={() => onChange(prevMonthLast)} aria-label="Предыдущий месяц">
            ‹
          </button>
          <span className="month-cal__title">{formatMonthTitle(date)}</span>
          <button
            type="button"
            className="day-nav__arrow day-nav__arrow--small"
            onClick={() => onChange(nextMonthFirst)}
            aria-label="Следующий месяц"
          >
            ›
          </button>
        </div>
        <div className="month-cal__grid">
          {WEEKDAY_HEADERS.map((w) => (
            <span key={w} className="month-cal__weekday" aria-hidden="true">
              {w}
            </span>
          ))}
          {cells.map((iso, i) => {
            if (!iso) return <span key={`blank-${i}`} aria-hidden="true" />;
            const state = dayState(byDate.get(iso), iso, today);
            const day = Number(iso.slice(8));
            const remote = byDate.get(iso)?.day_type === "remote";
            return (
              <button
                key={iso}
                type="button"
                className={`month-cal__day is-${state}${iso === date ? " is-selected" : ""}${iso === today ? " is-today" : ""}`}
                aria-pressed={iso === date}
                aria-label={`${day}, ${STATE_TEXT[state]}${remote ? ", ЭФО" : ""}`}
                title={`${STATE_TEXT[state]}${remote ? " · ЭФО" : ""}`}
                onClick={() => onChange(iso)}
              >
                {day}
              </button>
            );
          })}
        </div>
        <p className="month-cal__legend" aria-hidden="true">
          <span className="legend-chip is-ok" /> вовремя
          <span className="legend-chip is-late" /> задним числом
          <span className="legend-chip is-missing" /> не сдано
          <span className="legend-chip is-off" /> нерабочий
          <span className="legend-chip is-planned" /> запланировано
        </p>
      </div>
    </div>
  );
}
