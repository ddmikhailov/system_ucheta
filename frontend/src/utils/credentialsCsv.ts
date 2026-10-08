export interface Credential {
  full_name: string;
  department: string;
  username: string;
  password: string;
}

/** Список временных паролей — CSV для Excel (UTF-8 с BOM, разделитель «;»); создаётся в браузере, на сервере не хранится. */
export function credentialsCsv(rows: Credential[]): string {
  const cell = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const lines = [
    ["ФИО", "Отделение", "Логин", "Временный пароль"],
    ...rows.map((r) => [r.full_name, r.department, r.username, r.password]),
  ];
  return "\uFEFF" + lines.map((l) => l.map(cell).join(";")).join("\r\n");
}
