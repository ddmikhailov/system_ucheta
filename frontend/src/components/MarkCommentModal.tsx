import { useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";

/** Комментарий/основание к отметке — вынесены в отдельный диалог вместо
 * инпутов прямо в строке таблицы, чтобы строка статуса оставалась в одну
 * строку (не разъезжалась при выборе кода). */
export default function MarkCommentModal({
  comment,
  basisReference,
  requiresDocument,
  lastEditedInfo,
  onSave,
  onClose,
}: {
  comment: string;
  basisReference: string;
  requiresDocument: boolean;
  lastEditedInfo?: string | null;
  onSave: (comment: string, basisReference: string) => void;
  onClose: () => void;
}) {
  const [commentValue, setCommentValue] = useState(comment);
  const [basisValue, setBasisValue] = useState(basisReference);
  useEscapeKey(onClose);

  function save() {
    onSave(commentValue, basisValue);
    onClose();
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Комментарий" onClick={(e) => e.stopPropagation()}>
        <h3>Комментарий</h3>
        <label>
          Комментарий
          <input
            value={commentValue}
            onChange={(e) => setCommentValue(e.target.value)}
            placeholder="комментарий"
            autoFocus
          />
        </label>
        {requiresDocument && (
          <label>
            Основание
            <input
              value={basisValue}
              onChange={(e) => setBasisValue(e.target.value)}
              placeholder="№ приказа / справки (необязательно)"
            />
          </label>
        )}
        {lastEditedInfo && <p className="hint">Кто и когда внёс: {lastEditedInfo}</p>}
        <div className="actions">
          <button onClick={onClose}>Отмена</button>
          <button onClick={save}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}
