import { downloadFile } from "../api/client";
import type { DossierNote } from "../api/types";

/** Скачать протокол беседы по записи индивидуальной работы (бланк колледжа в Word). */
export function downloadProtocol(studentId: number, note: Pick<DossierNote, "id" | "occurred_on">): Promise<void> {
  return downloadFile(`/students/${studentId}/dossier/notes/${note.id}/protocol`, `Протокол_беседы_${note.occurred_on ?? ""}.docx`);
}
