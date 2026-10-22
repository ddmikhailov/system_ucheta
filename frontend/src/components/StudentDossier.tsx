import { useState } from "react";
import { useDossier, type DossierSectionKey, type DossierState } from "../hooks/useDossier";
import StudentCardModal from "./StudentCardModal";
import { ProfileForm } from "./dossier/ProfileForm";
import { Guardians } from "./dossier/Guardians";
import { Notes } from "./dossier/Notes";
import { AccessLog } from "./dossier/AccessLog";

/** Один раздел досье: основное и соц. статус, представители, записи индивидуальной работы
 * или журнал просмотров (последний — только администратору/тьютору). */
export function DossierSection({
  state,
  section,
  studentId,
  isAdmin,
  showMessages = true,
}: {
  state: DossierState;
  section: DossierSectionKey;
  studentId: number;
  isAdmin: boolean;
  /** Ошибки и «сохранено» над разделом; досье целиком показывает их один раз сверху. */
  showMessages?: boolean;
}) {
  const { dossier, error, notice, setDossier, setError, setNotice, load } = state;
  const [cardOpen, setCardOpen] = useState(false);
  if (section === "log") return isAdmin ? <AccessLog studentId={studentId} /> : null;
  if (error && !dossier) return <div className="error-text">{error}</div>;
  if (!dossier) return <p className="hint">Загрузка досье…</p>;

  return (
    <div>
      {showMessages && error && <div className="error-text">{error}</div>}
      {showMessages && notice && <div className="day-status submitted">{notice}</div>}
      {section === "profile" && (
        <div className="dossier-toolbar">
          <p className="hint">Заполненное показывается готовой информацией, изменить — кнопкой «Редактировать» в разделе.</p>
          <button type="button" className="btn-secondary" onClick={() => setCardOpen(true)} title="Бланк колледжа в Word: выберите, какие поля заполнить">
            Личная карточка в Word
          </button>
        </div>
      )}
      {section === "profile" && cardOpen && (
        <StudentCardModal
          endpoint={`/students/${studentId}/dossier/card`}
          heading="Личная карточка обучающегося"
          filename={`Личная_карточка_${studentId}.docx`}
          onClose={() => setCardOpen(false)}
        />
      )}
      {section === "profile" && (
        <ProfileForm
          // Форма берёт значения из досье один раз; после сохранения key пересоздаёт её.
          key={JSON.stringify([dossier.profile, dossier.special])}
          dossier={dossier}
          onSaved={(d) => {
            setDossier(d);
            setError(null);
            setNotice("Досье сохранено");
          }}
          onError={setError}
        />
      )}
      {section === "guardians" && <Guardians dossier={dossier} studentId={studentId} onChanged={load} onError={setError} />}
      {section === "notes" && <Notes dossier={dossier} studentId={studentId} onChanged={load} onError={setError} />}
    </div>
  );
}

// Досье студента целиком: контакты, представители, особые данные (шифруются на сервере),
// заметки куратора. Журнал просмотров — только администратору/тьютору.
export default function StudentDossier({ studentId, isAdmin }: { studentId: number; isAdmin: boolean }) {
  const state = useDossier(studentId);
  if (state.error && !state.dossier) return <div className="error-text">{state.error}</div>;
  if (!state.dossier) return <p className="hint">Загрузка досье…</p>;
  return (
    <div>
      {state.error && <div className="error-text">{state.error}</div>}
      {state.notice && <div className="day-status submitted">{state.notice}</div>}
      {(["profile", "guardians", "notes", "log"] as const).map((section) => (
        <DossierSection key={section} state={state} section={section} studentId={studentId} isAdmin={isAdmin} showMessages={false} />
      ))}
    </div>
  );
}
