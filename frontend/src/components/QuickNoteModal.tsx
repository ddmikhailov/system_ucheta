import { useEscapeKey } from "../hooks/useEscapeKey";
import NoteForm from "./NoteForm";

/** Запись об индивидуальной работе прямо из «Моего дня» (кнопка «Записать» у студента из группы риска), без
 * захода в карточку: та же форма, что в карточке студента, — с полями протокола беседы и кнопкой «Сохранить и
 * скачать протокол», чтобы сразу провести беседу под протокол. */
export default function QuickNoteModal({
  studentId,
  studentName,
  onSaved,
  onClose,
}: {
  studentId: number;
  studentName: string;
  onSaved: (withProtocol: boolean) => void;
  onClose: () => void;
}) {
  useEscapeKey(onClose);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-label="Запись индивидуальной работы"
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Запись: {studentName}</h3>
        <NoteForm studentId={studentId} autoFocus onCancel={onClose} onSaved={(_note, withProtocol) => onSaved(withProtocol)} />
      </div>
    </div>
  );
}
