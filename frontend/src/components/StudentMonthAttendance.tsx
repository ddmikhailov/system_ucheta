import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { StudentDayAttendance, StudentMonthAttendance } from "../api/types";

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

const NONWORKING_LABELS: Record<string, string> = {
  weekend: "выходной",
  holiday: "праздник",
  vacation: "каникулы",
  not_enrolled: "не числился",
};

function monthKey(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function monthLabel(year: number, month: number): string {
  const text = new Date(year, month - 1, 1).toLocaleString("ru-RU", { month: "long", year: "numeric" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")} ${WEEKDAYS[new Date(y, m - 1, d).getDay()]}`;
}

function statusText(day: StudentDayAttendance): string {
  switch (day.status) {
    case "present":
      return "Присутствовал";
    case "mark":
      return `${(day.mark_code ?? "").toUpperCase()} — ${day.mark_name ?? ""}`;
    case "not_submitted":
      return "День не сдан группой";
    default:
      return NONWORKING_LABELS[day.day_type] ?? "—";
  }
}

function rowClass(day: StudentDayAttendance): string {
  if (day.status === "none") return "day-nonworking";
  if (day.status === "not_submitted") return "day-not-submitted";
  if (day.status === "mark" && day.counts_as_present === false) return "day-absent";
  return "";
}

/** Посещаемость студента по дням с листанием по месяцам — доступна всем
 * ролям, которым открыта карточка студента. */
export default function StudentMonthAttendanceView({ studentId }: { studentId: number }) {
  const now = new Date();
  const [cursor, setCursor] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [showNonWorking, setShowNonWorking] = useState(false);
  const [result, setResult] = useState<{
    key: string;
    data: StudentMonthAttendance | null;
    error: string | null;
  } | null>(null);

  const requestKey = `${studentId}|${monthKey(cursor.year, cursor.month)}`;

  useEffect(() => {
    let cancelled = false;
    api
      .get<StudentMonthAttendance>(`/students/${studentId}/attendance?year=${cursor.year}&month=${cursor.month}`)
      .then((data) => {
        if (!cancelled) setResult({ key: requestKey, data, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({ key: requestKey, data: null, error: err instanceof ApiError ? err.message : "Ошибка загрузки" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, cursor.year, cursor.month, requestKey]);

  const current = result?.key === requestKey ? result : null;
  const data = current?.data ?? null;

  const currentKey = monthKey(now.getFullYear(), now.getMonth() + 1);
  const viewKey = monthKey(cursor.year, cursor.month);
  const canGoNext = viewKey < currentKey;
  const canGoPrev = !data || viewKey > data.first_month;

  function shift(delta: number) {
    setCursor((c) => {
      const d = new Date(c.year, c.month - 1 + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1 };
    });
  }

  const visibleDays = (data?.days ?? []).filter((d) => showNonWorking || d.status !== "none");
  const summary = data?.summary;

  return (
    <div>
      <h3 className="student-card__section">Посещаемость по месяцам</h3>
      <div className="month-nav">
        <button onClick={() => shift(-1)} disabled={!canGoPrev} aria-label="Предыдущий месяц">
          ←
        </button>
        <span className="month-nav__label">{monthLabel(cursor.year, cursor.month)}</span>
        <button onClick={() => shift(1)} disabled={!canGoNext} aria-label="Следующий месяц">
          →
        </button>
        <label className="hint">
          <input type="checkbox" checked={showNonWorking} onChange={(e) => setShowNonWorking(e.target.checked)} />{" "}
          показывать выходные
        </label>
      </div>

      {current?.error && <div className="error-text">{current.error}</div>}
      {!current && <p className="hint">Загрузка…</p>}

      {summary && (
        <p className="hint">
          Учебных дней: {summary.study_days} · присутствовал: {summary.present} · отсутствовал: {summary.absent}
          {summary.absent > 0 && ` (уваж. ${summary.absent_excused}, неуваж. ${summary.absent_unexcused})`} ·
          опозданий: {summary.late}
          {summary.not_submitted > 0 && ` · не сдано группой: ${summary.not_submitted}`}
          {summary.percent !== null && ` · посещаемость: ${summary.percent}%`}
        </p>
      )}

      {data && (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Статус</th>
              <th>Комментарий</th>
              <th>Основание</th>
            </tr>
          </thead>
          <tbody>
            {visibleDays.map((d) => (
              <tr key={d.date} className={rowClass(d)}>
                <td data-label="Дата">{dayLabel(d.date)}</td>
                <td data-label="Статус">{statusText(d)}</td>
                <td data-label="Комментарий">{d.comment ?? "—"}</td>
                <td data-label="Основание">{d.basis_reference ?? "—"}</td>
              </tr>
            ))}
            {visibleDays.length === 0 && (
              <tr>
                <td colSpan={4}>За этот месяц нет учебных дней.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
