// Минимальная длина пароля — как на бэкенде (backend/app/core/password_policy.py: MIN_PASSWORD_LENGTH).
// Совпадение проверяет backend/tests/test_frontend_roles_contract.py.
export const MIN_PASSWORD_LENGTH = 10;

// Требования, которые форма показывает и проверяет сразу. Окончательное решение — за сервером:
// он же отсекает последовательности (abc, 123, qwer), повторы (aaa), логин/ФИО и распространённые пароли.
export interface PasswordRule {
  label: string;
  ok: boolean;
}

export function passwordRules(password: string): PasswordRule[] {
  const chars = [...password];
  return [
    { label: `Не короче ${MIN_PASSWORD_LENGTH} символов`, ok: chars.length >= MIN_PASSWORD_LENGTH },
    { label: "Строчная буква", ok: chars.some((c) => c !== c.toUpperCase()) },
    { label: "Заглавная буква", ok: chars.some((c) => c !== c.toLowerCase()) },
    { label: "Цифра", ok: /\d/.test(password) },
    { label: "Спецсимвол: ! # $ % & * ?", ok: chars.some((c) => !/[\p{L}\p{N}\s]/u.test(c)) },
  ];
}

export function passwordRulesMet(password: string): boolean {
  return passwordRules(password).every((r) => r.ok);
}

export const PASSWORD_EXTRA_HINT =
  "Нельзя: подряд идущие буквы, цифры или клавиши (abc, 123, qwer), один символ три раза подряд, " +
  "логин или ФИО, распространённые пароли (Password, Qwerty, Kurator2026).";
