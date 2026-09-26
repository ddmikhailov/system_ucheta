// Раньше был продублирован дословно в 6 файлах (см. TODO.md 5).
export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
