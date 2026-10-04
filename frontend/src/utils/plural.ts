/** Склонение по числу: plural(1, ["день", "дня", "дней"]) → «день», 2 → «дня», 5 → «дней», 11 → «дней». */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last === 1) return forms[0];
  if (last >= 2 && last <= 4) return forms[1];
  return forms[2];
}
