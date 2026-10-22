import { api, ApiError } from "../../api/client";
import { NOTE_KINDS, PROTOCOL_KINDS } from "../../constants/noteKinds";
import { downloadProtocol } from "../../utils/protocol";
import NoteForm from "../NoteForm";
import { formatDateRu, formatServerDateTimeFull, todayIso } from "../../utils/date";
import type { Dossier, DossierNote } from "../../api/types";
import { dialogs, toast } from "../../utils/feedback";

export function Notes({
  dossier,
  studentId,
  onChanged,
  onError,
}: {
  dossier: Dossier;
  studentId: number;
  onChanged: () => void;
  onError: (e: string | null) => void;
}) {
  const base = `/students/${studentId}/dossier/notes`;

  function protocol(n: Pick<DossierNote, "id" | "occurred_on">) {
    downloadProtocol(studentId, n).catch((err) => onError(err instanceof ApiError ? err.message : "Не удалось сформировать протокол"));
  }

  async function setDone(id: number, done: boolean) {
    onError(null);
    try {
      await api.put(`${base}/${id}/follow-up`, { done });
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось изменить заметку");
    }
  }

  async function remove(id: number) {
    if (!(await dialogs.confirm("Удалить заметку?", { confirmLabel: "Удалить", danger: true }))) return;
    onError(null);
    try {
      await api.delete(`${base}/${id}`);
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось удалить заметку");
    }
  }

  return (
    <div className="dossier-form">
      <section className="dossier-section">
        <header className="dossier-section__head">
          <h4>Новая запись</h4>
          <p>Беседа, звонок, вызов родителей, договорённость — по ним можно сразу получить протокол беседы в Word.</p>
        </header>
        <NoteForm
          studentId={studentId}
          onSaved={(_note, withProtocol) => {
            onChanged();
            toast(withProtocol ? "Запись сохранена, протокол скачивается" : "Запись сохранена");
          }}
        />
      </section>

      <section className="dossier-section">
        <header className="dossier-section__head">
          <h4>
            Записи <span className="tabbar__badge">{dossier.notes.length}</span>
          </h4>
        </header>
        {dossier.notes.length === 0 ? (
          <p className="hint">Заметок пока нет.</p>
        ) : (
          <div className="note-list">
            {dossier.notes.map((n) => (
              <article key={n.id} className="note-card">
                <header className="note-card__head">
                  <span className="note-card__kind">{NOTE_KINDS[n.kind] ?? n.kind}</span>
                  <time>{n.occurred_on ? formatDateRu(n.occurred_on) : formatServerDateTimeFull(n.created_at)}</time>
                  <span className="hint">{n.author_name ?? "—"}</span>
                </header>
                <p className="note-card__text">{n.text}</p>
                {(n.goal || n.participants || n.result) && (
                  <dl className="note-card__details">
                    {n.goal && (
                      <div>
                        <dt>Цель</dt>
                        <dd>{n.goal}</dd>
                      </div>
                    )}
                    {n.participants && (
                      <div>
                        <dt>Присутствовали</dt>
                        <dd>{n.participants.split("\n").join("; ")}</dd>
                      </div>
                    )}
                    {n.result && (
                      <div>
                        <dt>Итог</dt>
                        <dd>{n.result}</dd>
                      </div>
                    )}
                  </dl>
                )}
                {n.follow_up_on && (
                  <div className={`note-card__follow${!n.follow_up_done && n.follow_up_on < todayIso() ? " is-overdue" : ""}`}>
                    {n.follow_up_done ? (
                      <span>Вернуться к вопросу: выполнено</span>
                    ) : (
                      <span>
                        Вернуться к вопросу до {formatDateRu(n.follow_up_on)}
                        {n.follow_up_on < todayIso() ? " (просрочено)" : ""}
                      </span>
                    )}
                    <button type="button" className="link-btn" onClick={() => setDone(n.id, !n.follow_up_done)}>
                      {n.follow_up_done ? "Вернуть в работу" : "Выполнено"}
                    </button>
                  </div>
                )}
                {(PROTOCOL_KINDS.includes(n.kind) || n.can_delete) && (
                  <footer className="note-card__actions">
                    {PROTOCOL_KINDS.includes(n.kind) && (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => protocol(n)}
                        title="Протокол беседы по образцу колледжа — можно распечатать или править в Word"
                      >
                        Протокол беседы (Word)
                      </button>
                    )}
                    {n.can_delete && (
                      <button type="button" className="link-btn danger-link" onClick={() => remove(n.id)}>
                        Удалить
                      </button>
                    )}
                  </footer>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
