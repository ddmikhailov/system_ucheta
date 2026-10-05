import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { useEscapeKey } from "../hooks/useEscapeKey";
import type { CuratorDaysRead } from "../api/types";
import { formatDateRu, formatDayMonthRu } from "../utils/date";

const STATUS_LABELS: Record<string, string> = {
  on_time: "вовремя",
  late: "задним числом",
  missed: "не сдано",
};

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

function weekday(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return WEEKDAYS[new Date(y, m - 1, d).getDay()];
}

// Время приходит уже в местном времени колледжа (YYYY-MM-DDTHH:MM:SS без
// пояса) — разбираем строку, а не Date, чтобы браузер не сдвинул часы.
function formatSubmitted(localIso: string, dayIso: string): string {
  const [date, time] = localIso.split("T");
  const hhmm = time.slice(0, 5);
  return date === dayIso ? hhmm : `${formatDayMonthRu(date)} ${hhmm}`;
}

/** Разбор дисциплины одной группы по дням — только для зав. отделением:
 * когда куратор сдавал каждый день и кто именно сдал. */
export default function CuratorDaysModal({
  studyGroupId,
  dateFrom,
  dateTo,
  onClose,
}: {
  studyGroupId: number;
  dateFrom: string;
  dateTo: string;
  onClose: () => void;
}) {
  const [result, setResult] = useState<{ key: string; data: CuratorDaysRead | null; error: string | null } | null>(
    null,
  );
  useEscapeKey(onClose);

  const requestKey = `${studyGroupId}|${dateFrom}|${dateTo}`;
  useEffect(() => {
    let cancelled = false;
    api
      .get<CuratorDaysRead>(
        `/dashboards/curator-discipline/${studyGroupId}/days?date_from=${dateFrom}&date_to=${dateTo}`,
      )
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
  }, [studyGroupId, dateFrom, dateTo, requestKey]);

  const current = result?.key === requestKey ? result : null;
  const data = current?.data ?? null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label="Дисциплина по дням"
        onClick={(e) => e.stopPropagation()}
      >
        {current?.error && <div className="error-text">{current.error}</div>}
        {!current && <p className="hint">Загрузка…</p>}
        {data && (
          <>
            <h3>
              {data.group_code} — {data.responsible_name ?? "нет куратора"}
            </h3>
            <p className="hint">
              {formatDateRu(data.date_from)}–{formatDateRu(data.date_to)}: вовремя {data.on_time}, задним числом{" "}
              {data.late}, не сдано {data.missed} из {data.total_study_days} учебных дней.
              {data.average_on_time_submission && ` В среднем день сдаётся около ${data.average_on_time_submission}.`}
            </p>
            <p className="hint">Время — последняя сдача дня (при пересдаче обновляется), по времени колледжа.</p>
            <div className="table-scroll">
              <table className="dash-table">
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Статус</th>
                    <th>Сдано в</th>
                    <th>Кто сдал</th>
                    <th>Пара</th>
                  </tr>
                </thead>
                <tbody>
                  {data.days.map((d) => (
                    <tr key={d.date} className={d.status === "missed" ? "not-submitted-row" : ""}>
                      <td data-label="Дата">
                        {formatDateRu(d.date)} <span className="hint">{weekday(d.date)}</span>
                      </td>
                      <td data-label="Статус">
                        {STATUS_LABELS[d.status] ?? d.status}
                        {d.status === "late" && d.days_late ? ` (+${d.days_late} дн.)` : ""}
                      </td>
                      <td data-label="Сдано в">{d.submitted_at_local ? formatSubmitted(d.submitted_at_local, d.date) : "—"}</td>
                      <td data-label="Кто сдал">{d.submitted_by ?? "—"}</td>
                      <td data-label="Пара">{d.first_period ?? "—"}</td>
                    </tr>
                  ))}
                  {data.days.length === 0 && (
                    <tr>
                      <td colSpan={5}>За выбранный период нет учебных дней.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
        <div className="actions">
          <button onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}
