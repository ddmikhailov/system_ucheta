import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { StudentDeletionRequest } from "../api/types";
import { dialogs } from "../utils/feedback";

/** Куратор не стирает студента сам: просит об этом администратора или зав. отделением. Блок в карточке
 * отчисленного/академ. студента — форма запроса либо состояние уже отправленного. */
export default function StudentDeletionRequestBox({ studentId }: { studentId: number }) {
  const [request, setRequest] = useState<StudentDeletionRequest | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<StudentDeletionRequest | null>(`/student-deletions/for-student/${studentId}`)
      .then(setRequest)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить запрос"));
  }, [studentId]);

  useEffect(load, [load]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!(await dialogs.confirm("Отправить запрос на полное удаление студента? Решит администратор или зав. отделением.", { confirmLabel: "Отправить" }))) return;
    setBusy(true);
    setError(null);
    try {
      setRequest(await api.post<StudentDeletionRequest>("/student-deletions", { student_id: studentId, reason }));
      setReason("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить запрос");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!request) return;
    setBusy(true);
    try {
      await api.post(`/student-deletions/${request.id}/cancel`, {});
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отозвать запрос");
    } finally {
      setBusy(false);
    }
  }

  const pending = request?.status === "pending";
  return (
    <section className="add-block" aria-label="Удаление студента">
      <p className="add-block__title">Удаление студента навсегда</p>
      {pending ? (
        <>
          <p className="hint">Запрос отправлен и ждёт решения: «{request.reason}».</p>
          <button onClick={cancel} disabled={busy}>
            Отозвать запрос
          </button>
        </>
      ) : (
        <form onSubmit={send}>
          {request?.status === "rejected" && (
            <p className="hint">Прошлый запрос отклонён{request.review_comment ? `: ${request.review_comment}` : ""}.</p>
          )}
          <p className="hint">
            Сотрутся студент, его отметки посещаемости и вся история. Куратор может только попросить об этом — удаляет администратор или
            зав. отделением.
          </p>
          <div className="inline-form">
            <input placeholder="Причина (обязательно)" aria-label="Причина" value={reason} onChange={(e) => setReason(e.target.value)} minLength={3} maxLength={500} required />
            <button type="submit" disabled={busy}>
              Запросить удаление
            </button>
          </div>
        </form>
      )}
      {error && <div className="error-text">{error}</div>}
    </section>
  );
}
