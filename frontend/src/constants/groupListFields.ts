// Столбцы «Списка группы» для печати — зеркало `FIELDS` в backend/app/services/group_list_service.py
// (ключи и подписи совпадают; контрактный тест tests/test_group_list.py держит серверную сторону).
// Особые категории досье (здоровье, соц. статус, учёт) в список не входят вообще.
export interface GroupListField {
  key: string;
  label: string;
  hint?: string;
}

export const GROUP_LIST_FIELDS: GroupListField[] = [
  { key: "full_name", label: "ФИО" },
  { key: "birth_date", label: "Дата рождения" },
  { key: "phone", label: "Телефон" },
  { key: "email", label: "E-mail" },
  { key: "messenger", label: "Мессенджер" },
  { key: "registration_address", label: "Адрес регистрации" },
  { key: "residence_address", label: "Адрес проживания" },
  { key: "guardians", label: "Представители" },
  { key: "guardian_phones", label: "Телефоны представителей" },
  { key: "funding", label: "Бюджет / договор" },
  { key: "additional_education", label: "Доп. образование" },
  { key: "status", label: "Статус" },
  { key: "enrolled_at", label: "Зачислен" },
  { key: "signature", label: "Подпись", hint: "пустой столбец для подписи от руки" },
  { key: "note", label: "Примечание", hint: "пустой столбец для заметок от руки" },
];

/** Готовые наборы — самые частые списки. */
export const GROUP_LIST_PRESETS: { label: string; keys: string[] }[] = [
  { label: "Только ФИО", keys: ["full_name"] },
  { label: "ФИО, телефон, e-mail", keys: ["full_name", "phone", "email"] },
  { label: "С представителями", keys: ["full_name", "guardians", "guardian_phones"] },
  { label: "Для подписи", keys: ["full_name", "signature"] },
];
