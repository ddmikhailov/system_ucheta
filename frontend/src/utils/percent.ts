/** Процент для людей: «86,7 %», целое без дроби — «70 %»; нет данных — «—». */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} %`;
}
