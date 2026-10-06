// Поля «Личной карточки обучающегося» (Word) — зеркало `FIELDS` в backend/app/services/student_card_service.py
// (ключи и подписи совпадают; контрактный тест tests/test_student_card.py держит серверную сторону).
// Особые категории досье (здоровье, соц. статус, учёт) в карточку не входят вообще.
export interface StudentCardField {
  key: string;
  label: string;
  hint?: string;
}

export const STUDENT_CARD_FIELDS: StudentCardField[] = [
  { key: "full_name", label: "ФИО" },
  { key: "group", label: "Группа" },
  { key: "gender", label: "Пол", hint: "в бланке подчёркивается нужное слово" },
  { key: "birth_date", label: "Дата рождения" },
  { key: "birth_place", label: "Место рождения", hint: "заполняется в досье" },
  { key: "registration_address", label: "Адрес регистрации" },
  { key: "enrollment_order", label: "Приказ о зачислении", hint: "заполняется в досье" },
  { key: "previous_education", label: "Образование до поступления", hint: "заполняется в досье" },
  { key: "absences", label: "Число пропущенных занятий (по семестрам)", hint: "дни с пропусками по журналу платформы" },
  { key: "social_work", label: "Общественная работа (доп. образование)", hint: "из «Дополнительного образования» в досье" },
];

export const STUDENT_CARD_PRESETS: { label: string; keys: string[] }[] = [
  { label: "Всё из платформы", keys: STUDENT_CARD_FIELDS.map((f) => f.key) },
  { label: "ФИО и группа (остальное — от руки)", keys: ["full_name", "group"] },
];
