import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { useEscapeKey } from "../hooks/useEscapeKey";
import type { DeleteResult, GroupDeletionPreview } from "../api/types";

/** Полное удаление группы вместе со студентами и всей посещаемостью.
 * Необратимо, поэтому перед кнопкой показываем, что именно исчезнет, и
 * просим ввести код группы. */
export default function DeleteGroupForeverModal({
  groupId,
  groupCode,
  onClose,
  onDeleted,
}: {
  groupId: number;
  groupCode: string;
  onClose: () => void;
  onDeleted: (detail: string) => void;
}) {
  const [preview, setPreview] = useState<GroupDeletionPreview | null>(null);
  const [typedCode, setTypedCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscapeKey(onClose);

  useEffect(() => {
    api
      .get<GroupDeletionPreview>(`/admin/groups/${groupId}/deletion-preview`)
      .then(setPreview)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить данные группы"));
  }, [groupId]);

  async function confirmDelete() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.delete<DeleteResult>(
        `/admin/groups/${groupId}?force=true&confirm_code=${encodeURIComponent(typedCode)}`
      );
      onDeleted(res.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить группу");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Удаление группы ${groupCode}`}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Удалить группу {groupCode} навсегда</h3>
        <p className="hint">Это необратимо. Будет удалено:</p>
        {preview ? (
          <ul>
            <li>студентов: {preview.students}</li>
            <li>отметок посещаемости: {preview.attendance_marks}</li>
            <li>сданных дней: {preview.day_submissions}</li>
            <li>длительных отсутствий: {preview.absence_periods}</li>
            <li>назначений кураторов: {preview.curator_assignments}</li>
          </ul>
        ) : (
          !error && <p className="hint">Загрузка…</p>
        )}
        <label>
          Для подтверждения введите код группы: <b>{groupCode}</b>
          <input value={typedCode} onChange={(e) => setTypedCode(e.target.value)} autoFocus />
        </label>
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button onClick={onClose}>Отмена</button>
          <button className="danger-btn" onClick={confirmDelete} disabled={busy || !preview || typedCode !== groupCode}>
            Удалить навсегда
          </button>
        </div>
      </div>
    </div>
  );
}
