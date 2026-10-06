import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { AttendanceChange } from "../../api/types";
import { formatDateRu, formatServerDateTimeFull } from "../../utils/date";
import { dialogs, toast } from "../../utils/feedback";

function code(c: string | null): string {
  return c ? c.toUpperCase() : "был";
}

/** Исправление прошлого дня: кто просит, почему и что меняется у каждого студента. Автор может
 * отозвать запрос, зав. отделением — одобрить или отклонить (с комментарием). */
export default function ChangeCard({
  change,
  canCancel,
  canReview,
  showDay,
  onDone,
  onOpenDay,
}: {
  change: AttendanceChange;
  canCancel?: boolean;
  canReview?: boolean;
  /** В общем списке на проверку — группа и дата в заголовке и ссылка на день. */
  showDay?: boolean;
  onDone: () => void;
  onOpenDay?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: "approve" | "reject" | "cancel") {
    let body: { comment: string | null } | undefined;
    if (action === "reject") {
      const comment = await dialogs.prompt("Почему исправление отклонено? Куратор увидит этот комментарий.", "", {
        confirmLabel: "Отклонить",
      });
      if (comment === null) return;
      if (!comment.trim()) {
        setError("Напишите, почему исправление отклонено");
        return;
      }
      body = { comment };
    } else if (action === "approve") {
      if (!(await dialogs.confirm("Применить исправление к журналу?", { confirmLabel: "Одобрить" }))) return;
      body = { comment: null };
    } else if (!(await dialogs.confirm("Отозвать запрос на исправление?", { confirmLabel: "Отозвать" }))) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post(`/attendance-changes/${change.id}/${action}`, body);
      toast(action === "approve" ? "Исправление применено" : action === "reject" ? "Исправление отклонено" : "Запрос отозван");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось выполнить действие");
    } finally {
      setBusy(false);
    }
  }

  const decided = change.status !== "pending";
  return (
    <article className={`change-card is-${change.status}`}>
      <header className="change-card__head">
        <span className={`status-pill is-${change.status}`}>
          {change.status === "pending" ? "На проверке" : change.status === "approved" ? "Одобрено" : change.status === "rejected" ? "Отклонено" : "Отозвано"}
        </span>
        <b>
          {showDay ? `${change.group_code} · ${formatDateRu(change.date)} — ` : "Исправление дня — "}
          {change.requested_by_name}
        </b>
        <span className="hint">{formatServerDateTimeFull(change.created_at)}</span>
      </header>
      <p className="change-card__reason">
        <span className="hint">Причина:</span> {change.reason}
      </p>
      {change.changes.length > 0 && (
        <ul className="change-card__list">
          {change.changes.map((c) => (
            <li key={c.student_id}>
              <span>{c.full_name}</span>
              <span className="change-card__codes">
                {c.details_changed ? (
                  <>комментарий или основание</>
                ) : (
                  <>
                    {code(c.from_code)} <span aria-label="станет">→</span> <b>{c.to_code ? c.to_code.toUpperCase() : "присутствовал"}</b>
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {!decided && change.changes.length === 0 && <p className="hint">Отметки не меняются{change.first_period ? " (только пара)" : ""}.</p>}
      {decided && change.reviewed_by_name && (
        <p className="hint">
          {change.reviewed_by_name}
          {change.reviewed_at ? `, ${formatServerDateTimeFull(change.reviewed_at)}` : ""}
          {change.review_comment ? ` — «${change.review_comment}»` : ""}
        </p>
      )}
      {error && <div className="error-text">{error}</div>}
      {!decided && (canCancel || canReview || onOpenDay) && (
        <div className="change-card__actions">
          {canReview && (
            <>
              <button type="button" className="btn-primary" onClick={() => act("approve")} disabled={busy}>
                Одобрить
              </button>
              <button type="button" className="btn-secondary" onClick={() => act("reject")} disabled={busy}>
                Отклонить
              </button>
            </>
          )}
          {canCancel && (
            <button type="button" className="btn-secondary" onClick={() => act("cancel")} disabled={busy}>
              Отозвать
            </button>
          )}
          {onOpenDay && (
            <button type="button" className="link-btn" onClick={onOpenDay}>
              Открыть день
            </button>
          )}
        </div>
      )}
    </article>
  );
}
