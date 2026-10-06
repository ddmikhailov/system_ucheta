import { Link } from "react-router-dom";
import type { MarkCodeOption, RosterResponse } from "../../api/types";
import { formatServerDateTimeFull } from "../../utils/date";
import { Kpi } from "../ProfileHero";

/** Итоги сданного дня вместо формы: сколько пришло, кто отсутствовал и почему, кто и когда сдал.
 * Форма открывается кнопкой «Редактировать» — так сданный день не правится случайным нажатием. */
export default function DaySummary({
  roster,
  markCodes,
  editLabel,
  onEdit,
  editDisabled,
}: {
  roster: RosterResponse;
  markCodes: MarkCodeOption[];
  editLabel: string;
  onEdit: () => void;
  editDisabled?: boolean;
}) {
  const byCode = new Map(markCodes.map((m) => [m.code, m]));
  const total = roster.entries.length;
  const marked = roster.entries.filter((e) => e.mark_code);
  const absent = marked.filter((e) => !byCode.get(e.mark_code!)?.counts_as_present);
  const excused = absent.filter((e) => byCode.get(e.mark_code!)?.is_excused).length;
  const presentWithMark = marked.length - absent.length; // опоздали, ушли с занятий и т. п.
  const present = total - absent.length;
  const percent = total ? Math.round((present * 100) / total) : 0;

  return (
    <section className="day-summary" aria-label="Итоги дня">
      <div className="day-summary__head">
        <div>
          <h3>Итоги дня</h3>
          <p className="hint">
            {roster.submitted_at ? `Сдан ${formatServerDateTimeFull(roster.submitted_at)}` : "Сдан"}
            {roster.submitted_by_name ? ` · ${roster.submitted_by_name}` : ""}
            {roster.is_on_time === false ? " · задним числом" : " · вовремя"}
            {roster.first_period ? ` · пришли к ${roster.first_period} паре` : ""}
          </p>
        </div>
        <button type="button" className="btn-secondary" onClick={onEdit} disabled={editDisabled}>
          {editLabel}
        </button>
      </div>

      <div className="kpi-row">
        <Kpi label="Присутствуют" value={`${present} из ${total}`} tone={percent >= 85 ? "ok" : percent >= 70 ? "warn" : "hot"} hint={`${percent} %`} />
        <Kpi label="Отсутствуют" value={String(absent.length)} tone={absent.length - excused > 0 ? "hot" : undefined} />
        <Kpi label="По уважительной" value={String(excused)} />
        <Kpi label="Без причины" value={String(absent.length - excused)} tone={absent.length - excused > 0 ? "hot" : undefined} />
        <Kpi label="Опоздания и др." value={String(presentWithMark)} />
      </div>

      {marked.length === 0 ? (
        <p className="day-summary__all">Все студенты присутствовали.</p>
      ) : (
        <table className="dash-table roster-table compact-cards day-summary__table">
          <thead>
            <tr>
              <th>Студент</th>
              <th>Отметка</th>
              <th>Комментарий</th>
            </tr>
          </thead>
          <tbody>
            {marked.map((e) => {
              const code = byCode.get(e.mark_code!);
              return (
                <tr key={e.student_id}>
                  <td data-label="Студент">
                    <Link className="link-btn" to={`/students/${e.student_id}`}>
                      {e.full_name}
                    </Link>
                  </td>
                  <td data-label="Отметка">
                    <span className={`mark-chip${code?.counts_as_present ? "" : code?.is_excused ? " is-excused" : " is-unexcused"}`}>
                      {e.mark_code!.toUpperCase()}
                    </span>{" "}
                    {e.mark_name ?? code?.name}
                    {e.is_locked && <span className="hint"> · период</span>}
                  </td>
                  <td data-label="Комментарий">
                    {[e.comment, e.basis_reference].filter(Boolean).join(" · ") || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
