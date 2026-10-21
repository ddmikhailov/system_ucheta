// Черновик отметок журнала в пределах вкладки браузера (sessionStorage): отметки, не сданные на сервер, раньше
// жили только в памяти страницы и пропадали при истёкшей сессии, перезагрузке, свайпе «назад» на телефоне или
// выгрузке вкладки браузером. Черновик привязан к пользователю, группе и дню и восстанавливается, только если
// день на сервере с тех пор не менялся (baseline) — иначе чужие или уже сданные отметки перетёрлись бы старыми.

export interface DraftMark {
  mark_code: string;
  comment: string;
  basis_reference: string;
}

export interface JournalDraft {
  /** Отметки формы: студент → отметка. */
  pending: Record<number, DraftMark>;
  firstPeriod: string;
  /** Отметки дня на сервере, от которых начиналась правка (JSON), и был ли день сдан. */
  baseline: string;
  submitted: boolean;
}

const PREFIX = "kait20:journal-draft:";

export function journalDraftKey(userId: number, groupId: number, date: string): string {
  return `${PREFIX}${userId}:${groupId}:${date}`;
}

export function readJournalDraft(key: string): JournalDraft | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const draft = JSON.parse(raw) as JournalDraft;
    return draft && typeof draft.pending === "object" && typeof draft.baseline === "string" ? draft : null;
  } catch {
    return null;
  }
}

export function saveJournalDraft(key: string, draft: JournalDraft): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(draft));
  } catch {
    // хранилище недоступно или переполнено — работаем без черновика, как раньше
  }
}

export function clearJournalDraft(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // нечего стирать
  }
}

function draftKeys(): string[] {
  try {
    return Object.keys(sessionStorage).filter((k) => k.startsWith(PREFIX));
  } catch {
    return [];
  }
}

/** Есть ли во вкладке несданные отметки — перед выходом стоит переспросить. */
export function hasJournalDrafts(): boolean {
  return draftKeys().length > 0;
}

/** Выход: черновики (в комментариях бывают сведения о студентах) не оставляем на общем компьютере. */
export function clearJournalDrafts(): void {
  for (const key of draftKeys()) clearJournalDraft(key);
}
