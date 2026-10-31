import { useMemo } from "react";
import type { CuratorCardRow } from "../../api/types";
import { filterByQuery } from "../../utils/searchMatch";
import { useEntryState } from "../../hooks/useEntryState";
import ResultsBar from "./ResultsBar";
import LoadState from "./LoadState";
import { useDashboardRows } from "./useDashboardRows";

const NO_CURATOR = "нет куратора";

function percent(value: number | null): string {
  return value === null ? "—" : `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} %`;
}

/** Группе нужно внимание заведующего: есть несданные дни или студенты в группе риска. Это не оценка куратора. */
function needsAttention(r: CuratorCardRow): boolean {
  return r.missed > 0 || r.risk_count > 0;
}

/** «Карточка куратора» (положение, п. 3.7): сводка по группе за период. Только цифры, без рейтинга. */
export default function CuratorCardTab({ dateFrom, dateTo, deptQuery, reloadKey }: {
  dateFrom: string;
  dateTo: string;
  deptQuery: string;
  reloadKey: number;
}) {
  const { rows, error, loading } = useDashboardRows<CuratorCardRow>(
    `/dashboards/curator-card?date_from=${dateFrom}&date_to=${dateTo}${deptQuery}`, reloadKey,
  );
  const [query, setQuery] = useEntryState("cardQuery", "");
  const [course, setCourse] = useEntryState<number | "all">("cardCourse", "all");
  const [onlyAttention, setOnlyAttention] = useEntryState("cardOnlyAttention", false);

  const courses = useMemo(() => Array.from(new Set(rows.map((r) => r.course))).sort((a, b) => a - b), [rows]);
  const filtered = query.trim() !== "" || course !== "all" || onlyAttention;
  const visible = useMemo(() => {
    let list = rows;
    if (course !== "all") list = list.filter((r) => r.course === course);
    if (onlyAttention) list = list.filter(needsAttention);
    return filterByQuery(list, query, (r) => `${r.code} ${r.responsible_name ?? NO_CURATOR}`);
  }, [rows, course, onlyAttention, query]);

  return (
    <>
      <LoadState error={error} loading={loading} />
      <p className="hint">
        Сводка по группе за выбранный период. Группа риска считается с начала семестра по конец периода.
        Цифры не складываются в оценку: это повод поговорить с куратором.
      </p>
      <div className="toolbar toolbar--filters">
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Группа или куратор" aria-label="Поиск по группе или куратору" />
        <select aria-label="Курс" value={course} onChange={(e) => setCourse(e.target.value === "all" ? "all" : Number(e.target.value))}>
          <option value="all">Все курсы</option>
          {courses.map((c) => (
            <option key={c} value={c}>Курс {c}</option>
          ))}
        </select>
        <label className="check-inline">
          <input type="checkbox" checked={onlyAttention} onChange={(e) => setOnlyAttention(e.target.checked)} /> Только требующие внимания
        </label>
      </div>
      <ResultsBar shown={visible.length} total={rows.length} filtered={filtered} onReset={() => { setQuery(""); setCourse("all"); setOnlyAttention(false); }} />
      <div className="curator-cards">
        {visible.map((r) => (
          <section key={r.study_group_id} className={`curator-card${needsAttention(r) ? " curator-card--attention" : ""}`} aria-label={`Карточка группы ${r.code}`}>
            <header className="curator-card__head">
              <h3>{r.code}</h3>
              <span>{r.responsible_name ?? NO_CURATOR} · курс {r.course} · студентов {r.students_count}</span>
            </header>
            <dl className="curator-card__metrics">
              <div><dt>Посещаемость</dt><dd>{percent(r.attendance_percent)}</dd></div>
              <div><dt>Пропуски без причины</dt><dd>{percent(r.absent_unexcused_percent)}</dd></div>
              <div><dt>Группа риска</dt><dd>{r.risk_count}</dd></div>
              <div><dt>Восполнить пропуски</dt><dd>{r.compensation_count}</dd></div>
              <div><dt>Сдано вовремя</dt><dd>{r.on_time} из {r.total_study_days}</dd></div>
              <div><dt>С опозданием</dt><dd>{r.late}</dd></div>
              <div><dt>Не сдано</dt><dd>{r.missed}</dd></div>
            </dl>
            <p className="curator-card__contingent">
              Контингент за период: пришло {r.contingent.joined}, выбыло {r.contingent.left},
              переведено к нам {r.contingent.transferred_in}, от нас {r.contingent.transferred_out};
              в академическом отпуске сейчас {r.contingent.academic_leave}.
            </p>
          </section>
        ))}
        {visible.length === 0 && (
          <p>{rows.length === 0 ? "Нет данных за выбранный период." : "Под выбранные фильтры ничего не подошло."}</p>
        )}
      </div>
    </>
  );
}
