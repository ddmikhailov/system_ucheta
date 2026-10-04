// Телефон из досье — свободный текст («+7 (900) 123-45-67», «8 900 1234567», «123-45-67 доб. 2»).
// Для ссылки «позвонить» оставляем цифры и ведущий «+»; если цифр слишком мало, это не номер — ссылки нет.
export function telHref(phone: string | null | undefined): string | null {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 5) return null;
  return `tel:${phone.trim().startsWith("+") ? "+" : ""}${digits}`;
}
