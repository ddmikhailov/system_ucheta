// Виды заметок досье / записей индивидуальной работы (backend: schemas/dossier.py, NoteIn.kind).
export const NOTE_KINDS: Record<string, string> = {
  conversation: "Беседа",
  call: "Звонок",
  parent_invited: "Вызов родителей",
  prevention_council: "Совет профилактики",
  home_visit: "Визит домой",
  incident: "Инцидент",
  agreement: "Договорённость",
  other: "Другое",
};

// Виды записей, из которых делается протокол беседы (зеркало conversation_protocol_service.PROTOCOL_KINDS).
export const PROTOCOL_KINDS = ["conversation", "call", "parent_invited", "agreement"];
