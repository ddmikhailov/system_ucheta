import { Link } from "react-router-dom";
import type { MarkCodeOption, RosterAbsencePeriod, RosterResponse } from "../../api/types";
import { formatPercent } from "../../utils/percent";
import MarkCodeButtons from "../MarkCodeButtons";

/** Несданная отметка студента в форме дня. */
export interface PendingMark {
  mark_code: string;
  comment: string;
  basis_reference: string;
}

/** Таблица отметок дня: статус, риск и «восполнить», комментарий и период отсутствия по каждому студенту. */
export default function RosterTable({ roster, pending, markCodes, thresholds, reviewMode, onMark, onComment, onPeriod }: {
  roster: RosterResponse;
  pending: Record<number, PendingMark>;
  markCodes: MarkCodeOption[];
  thresholds: { risk_unexcused_percent: number; risk_attendance_percent: number };
  reviewMode: boolean;
  onMark: (studentId: number, code: string | null) => void;
  onComment: (studentId: number) => void;
  /** Открыть период отсутствия: новый (period = null) или существующий для правки. */
  onPeriod: (studentId: number, period: RosterAbsencePeriod | null) => void;
}) {
  return (
    <table className="roster-table compact-cards journal-roster">
      <thead>
        <tr>
          <th>№</th>
          <th>ФИО</th>
          <th>Статус</th>
          <th>Комментарий</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {roster.entries.map((entry, index) => {
          const current = pending[entry.student_id];
          const code = current?.mark_code ?? null;
          const risky = entry.is_risk;
          const hasComment = Boolean(current?.comment || current?.basis_reference);
          return (
            <tr key={entry.student_id} className={risky ? "risk-row" : ""}>
              <td data-label="№">{index + 1}</td>
              <td data-label="ФИО">
                <Link to={`/students/${entry.student_id}`} className="link-btn">
                  {entry.full_name}
                </Link>
              </td>
              <td data-label="Статус">
                {entry.is_locked ? (
                  <span className="locked-badge" title={entry.basis_reference ?? ""}>
                    {entry.mark_name}
                  </span>
                ) : (
                  <MarkCodeButtons value={code} markCodes={markCodes} onChange={(c) => onMark(entry.student_id, c)} />
                )}
                {entry.is_draft_suggestion && !entry.is_locked && <span className="draft-badge">черновик со вчера</span>}
                {risky && (
                  <span
                    className="risk-badge"
                    title={`Группа риска: пропусков без уважительной причины с начала семестра больше ${thresholds.risk_unexcused_percent} %`}
                  >
                    риск: без уважительной причины {formatPercent(entry.unexcused_percent)}
                  </span>
                )}
                {entry.needs_compensation && (
                  <span
                    className="compensate-badge"
                    title={`Посещаемость с начала семестра ${formatPercent(entry.attendance_percent)}: без практики и ИУП ниже ${thresholds.risk_attendance_percent} %. Закрыть — на вкладке «Студенты».`}
                  >
                    восполнить пропуски
                  </span>
                )}
              </td>
              <td data-label="Комментарий">
                {!entry.is_locked && code && (
                  <button className="comment-btn" onClick={() => onComment(entry.student_id)}>
                    {hasComment ? "Комментарий добавлен" : "Добавить комментарий"}
                  </button>
                )}
              </td>
              <td>
                {!entry.is_locked && !reviewMode && (
                  <button className="link-btn" onClick={() => onPeriod(entry.student_id, null)}>
                    Период
                  </button>
                )}
                {entry.is_locked && entry.absence_period?.group_practice_id != null && (
                  <span className="hint">Практика группы</span>
                )}
                {entry.is_locked && entry.absence_period && entry.absence_period.group_practice_id == null && (
                  <button
                    className="link-btn"
                    onClick={() => onPeriod(entry.student_id, entry.absence_period ?? null)}
                  >
                    Редактировать
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
