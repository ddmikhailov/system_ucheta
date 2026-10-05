"""Массовая загрузка досье из Excel (этап 1): шаблон → заполнение →
предпросмотр с ошибками → применение.

Правила:
  * студент ищется по коду группы + ФИО (без учёта регистра и ё/е); отчество
    необязательно, если по фамилии и имени в группе однозначно;
  * пустая ячейка = «не менять» (стереть значение через импорт нельзя);
  * представители: «Представитель N» сопоставляется по ФИО (обновляется
    «кем приходится»/телефон), иначе добавляется;
  * особые поля (соц. статус, здоровье) требуют ключ шифрования;
  * зав. отделением и тьютор загружают только по группам своего отделения;
  * строки с ошибками пропускаются, остальные применяются.
"""
import datetime
import io
from dataclasses import dataclass, field
from itertools import islice

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.core import field_crypto
from app.core.roles import is_department_scoped
from app.core.xlsx import UnsafeArchiveError, append_row, check_zip_safety
from app.models import Student, StudentGuardian, StudentProfile, StudyGroup, User
from app.schemas.dossier import ProfileFields, SpecialData
from app.services.audit_service import log_action

MAX_ROWS = 5000
# Пустые «хвосты» листа (форматирование, удалённые строки) читаем с запасом, но не бесконечно:
# лист может объявить миллионы строк, а openpyxl честно пройдётся по каждой.
MAX_SCANNED_ROWS = MAX_ROWS + 2000
GUARDIAN_SLOTS = 2

# (ключ, заголовок, раздел) — раздел: id (опознание студента), profile, guardian, special.
ID_COLUMNS = [("group", "Группа"), ("last_name", "Фамилия"), ("first_name", "Имя"), ("middle_name", "Отчество")]
PROFILE_COLUMNS = [
    ("birth_date", "Дата рождения"),
    ("gender", "Пол (м/ж)"),
    ("funding", "Финансирование (бюджет/договор)"),
    ("phone", "Телефон"),
    ("email", "E-mail"),
    ("messenger", "Мессенджер"),
    ("registration_address", "Адрес регистрации"),
    ("residence_address", "Адрес проживания"),
]
GUARDIAN_COLUMNS = [("name", "ФИО"), ("relation", "Кем приходится"), ("phone", "Телефон")]
SPECIAL_COLUMNS = [
    ("is_orphan", "Сирота (да/нет)"),
    ("under_guardianship", "Под опекой (да/нет)"),
    ("disability_group", "Группа инвалидности"),
    ("has_ovz", "ОВЗ (да/нет)"),
    ("large_family", "Многодетная семья (да/нет)"),
    ("low_income", "Малоимущая семья (да/нет)"),
    ("pdn_kdn", "Учёт ПДН/КДН (да/нет)"),
    ("internal_record", "Внутренний учёт (да/нет)"),
    ("scholarship", "Стипендия / соцвыплаты"),
    ("health_note", "Здоровье"),
]
BOOL_SPECIAL = {"is_orphan", "under_guardianship", "has_ovz", "large_family", "low_income", "pdn_kdn", "internal_record"}

_TRUE = {"да", "д", "yes", "y", "true", "1", "+"}
_FALSE = {"нет", "н", "no", "n", "false", "0", "-"}
_FUNDING = {"бюджет": "budget", "budget": "budget", "договор": "contract", "контракт": "contract", "contract": "contract"}
_GENDER = {
    "м": "male", "муж": "male", "мужской": "male", "male": "male", "m": "male",
    "ж": "female", "жен": "female", "женский": "female", "female": "female", "f": "female",
}
# Колонки, появившиеся после выдачи первых шаблонов: файл со старым набором заголовков принимается
# (новых колонок в нём нет — они просто не загружаются), чтобы не ломать уже раздатые кураторам шаблоны.
_ADDED_COLUMNS = {"Пол (м/ж)"}


def _headers(legacy: bool = False) -> list[str]:
    """Заголовки шаблона; legacy — набор первой версии шаблона (без колонок из _ADDED_COLUMNS)."""
    headers = [h for _, h in ID_COLUMNS] + [h for _, h in PROFILE_COLUMNS]
    for n in range(1, GUARDIAN_SLOTS + 1):
        headers += [f"Представитель {n}: {h}" for _, h in GUARDIAN_COLUMNS]
    headers += [h for _, h in SPECIAL_COLUMNS]
    return [h for h in headers if not (legacy and h in _ADDED_COLUMNS)]


def _norm(value) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


@dataclass
class RowResult:
    row: int
    label: str
    student_id: int | None = None
    errors: list[str] = field(default_factory=list)
    profile: dict = field(default_factory=dict)
    special: dict = field(default_factory=dict)
    guardians: list[dict] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.profile or self.special or self.guardians)


def _students_in_scope(db: Session, user: User) -> list[Student]:
    q = db.query(Student).join(StudyGroup, StudyGroup.id == Student.study_group_id).filter(StudyGroup.is_active.is_(True))
    if is_department_scoped(user):
        q = q.filter(StudyGroup.department_id == user.department_id)
    return q.order_by(StudyGroup.code, Student.last_name, Student.first_name).all()


def build_template(db: Session, user: User) -> bytes:
    """Шаблон: студенты доступных групп уже вписаны (группа + ФИО), остальное пустое —
    данные студентов в файл не выгружаются."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Досье"
    headers = _headers()
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for s in _students_in_scope(db, user):
        append_row(ws, [s.study_group.code, s.last_name, s.first_name, s.middle_name or ""])
    for idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 22
    ws.freeze_panes = "E2"

    help_ws = wb.create_sheet("Инструкция")
    for line in [
        "Колонки «Группа», «Фамилия», «Имя», «Отчество» опознают студента — не меняйте их.",
        "Заполняйте только то, что нужно. Пустая ячейка = «не менять» (стереть значение через импорт нельзя).",
        "Дата рождения: ДД.ММ.ГГГГ. Пол: м или ж. Финансирование: бюджет или договор.",
        "Да/нет-поля: да, нет (или +, -, 1, 0).",
        "Представитель: ФИО и «кем приходится» нужны вместе; если такой представитель уже есть — обновится, иначе добавится.",
        "Соц. статус и здоровье — особые данные: хранятся зашифрованными, не отправляйте файл по почте и не оставляйте на общих дисках.",
        "Перед применением система покажет предпросмотр с ошибками; строки с ошибками пропускаются.",
    ]:
        help_ws.append([line])
    help_ws.column_dimensions["A"].width = 120
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ImportFileError(Exception):
    pass


def _parse_date(value) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"не распознана дата «{text}» (нужно ДД.ММ.ГГГГ)")


def _parse_gender(value) -> str:
    gender = _GENDER.get(_norm(value))
    if gender is None:
        raise ValueError(f"«{value}» — ожидалось м или ж")
    return gender


def _parse_bool(value) -> bool:
    text = _norm(value)
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"«{value}» — ожидалось да или нет")


def _limit(key: str, text: str) -> str:
    model = ProfileFields if key in ProfileFields.model_fields else SpecialData
    for meta in model.model_fields[key].metadata:
        max_length = getattr(meta, "max_length", None)
        if max_length is not None and len(text) > max_length:
            raise ValueError(f"слишком длинное значение (максимум {max_length} символов)")
    return text


def parse_workbook(db: Session, user: User, content: bytes) -> list[RowResult]:
    try:
        check_zip_safety(content)
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except UnsafeArchiveError as exc:
        raise ImportFileError(f"Файл не принят: {exc}. Нужен .xlsx, скачанный из шаблона") from exc
    except Exception as exc:  # битый/не xlsx файл
        raise ImportFileError("Не удалось прочитать файл — нужен .xlsx, скачанный из шаблона") from exc
    ws = wb["Досье"] if "Досье" in wb.sheetnames else wb.worksheets[0]
    # Читаем только нужные столбцы и ограниченное число строк (+1, чтобы заметить переполнение).
    rows = list(islice(ws.iter_rows(values_only=True, max_col=len(_headers())), MAX_SCANNED_ROWS + 1))
    if len(rows) > MAX_SCANNED_ROWS:
        raise ImportFileError(f"Слишком много строк на листе (максимум {MAX_ROWS})")
    if not rows:
        raise ImportFileError("Файл пустой")
    header = [_text(c) or "" for c in rows[0]]
    # Текущий шаблон либо шаблон первой версии (раздан раньше) — по заголовкам.
    expected = next((h for h in (_headers(), _headers(legacy=True)) if header[: len(h)] == h), None)
    if expected is None:
        raise ImportFileError("Заголовки не совпадают с шаблоном — скачайте шаблон заново и заполните его")
    data_rows = [(i, r) for i, r in enumerate(rows[1:], start=2) if any(c not in (None, "") for c in r)]
    if len(data_rows) > MAX_ROWS:
        raise ImportFileError(f"Слишком много строк (максимум {MAX_ROWS})")

    groups = {_norm(g.code): g for g in db.query(StudyGroup).all()}
    students_by_group: dict[int, list[Student]] = {}
    encryption_ok = field_crypto.is_available()
    results: list[RowResult] = []

    for line_no, row in data_rows:
        cells = list(row) + [None] * (len(expected) - len(row))
        values = dict(zip(expected, cells))
        group_code = _text(values["Группа"])
        last, first, middle = (_text(values[h]) for h in ("Фамилия", "Имя", "Отчество"))
        result = RowResult(row=line_no, label=" ".join(p for p in (group_code, last, first, middle) if p))
        results.append(result)

        group = groups.get(_norm(group_code)) if group_code else None
        if group is None:
            result.errors.append("группа не найдена")
            continue
        if is_department_scoped(user) and group.department_id != user.department_id:
            result.errors.append("группа не из вашего отделения")
            continue
        if not last or not first:
            result.errors.append("не указаны фамилия и имя")
            continue
        candidates = students_by_group.setdefault(
            group.id, db.query(Student).filter(Student.study_group_id == group.id).all()
        )
        matches = [s for s in candidates if _norm(s.last_name) == _norm(last) and _norm(s.first_name) == _norm(first)]
        if middle:
            matches = [s for s in matches if _norm(s.middle_name) == _norm(middle)]
        if not matches:
            result.errors.append("студент не найден в этой группе")
            continue
        if len(matches) > 1:
            result.errors.append("найдено несколько студентов — укажите отчество")
            continue
        result.student_id = matches[0].id

        def collect(key: str, header: str, target: dict, convert) -> None:
            raw = values[header]
            if raw is None or str(raw).strip() == "":
                return
            try:
                target[key] = convert(raw)
            except ValueError as exc:
                result.errors.append(f"{header}: {exc}")

        for key, header in PROFILE_COLUMNS:
            if header not in values:  # колонки нет в старом шаблоне
                continue
            if key == "birth_date":
                collect(key, header, result.profile, _parse_date)
            elif key == "gender":
                collect(key, header, result.profile, _parse_gender)
            elif key == "funding":
                def to_funding(raw):
                    value = _FUNDING.get(_norm(raw))
                    if value is None:
                        raise ValueError(f"«{raw}» — ожидалось бюджет или договор")
                    return value
                collect(key, header, result.profile, to_funding)
            else:
                collect(key, header, result.profile, lambda raw, k=key: _limit(k, _text(raw)))

        for key, header in SPECIAL_COLUMNS:
            collect(key, header, result.special, _parse_bool if key in BOOL_SPECIAL else lambda raw, k=key: _limit(k, _text(raw)))
        if result.special and not encryption_ok:
            result.errors.append("особые поля недоступны: на сервере не задан ключ шифрования")

        for n in range(1, GUARDIAN_SLOTS + 1):
            parts = {k: _text(values[f"Представитель {n}: {h}"]) for k, h in GUARDIAN_COLUMNS}
            if not any(parts.values()):
                continue
            if not parts["name"]:
                result.errors.append(f"Представитель {n}: не указано ФИО")
            elif len(parts["name"]) > 255 or len(parts["relation"] or "") > 64 or len(parts["phone"] or "") > 32:
                result.errors.append(f"Представитель {n}: слишком длинное значение")
            else:
                result.guardians.append(parts)
    return results


def apply_results(db: Session, user: User, results: list[RowResult]) -> int:
    """Применяет строки без ошибок. Возвращает число обновлённых студентов."""
    updated = 0
    for r in results:
        if r.errors or r.student_id is None or not r.has_changes:
            continue
        changed: list[str] = []
        profile = db.get(StudentProfile, r.student_id)
        if profile is None:
            profile = StudentProfile(student_id=r.student_id)
            db.add(profile)
        for key, value in r.profile.items():
            if getattr(profile, key) != value:
                setattr(profile, key, value)
                changed.append(key)

        if r.special:
            current = SpecialData(**field_crypto.decrypt_json(profile.special_enc)) if profile.special_enc else SpecialData()
            merged = SpecialData(**{**current.model_dump(), **r.special})
            if merged != current:
                profile.special_enc = field_crypto.encrypt_json(merged.model_dump())
                changed.append("special")

        if r.guardians:
            existing = db.query(StudentGuardian).filter(StudentGuardian.student_id == r.student_id).all()
            has_primary = any(g.is_primary for g in existing)
            for parts in r.guardians:
                match = next((g for g in existing if _norm(g.full_name) == _norm(parts["name"])), None)
                if match is None:
                    guardian = StudentGuardian(
                        student_id=r.student_id, full_name=parts["name"], relation=parts["relation"] or "не указано",
                        phone=parts["phone"], is_primary=not has_primary,
                    )
                    has_primary = True
                    db.add(guardian)
                    existing.append(guardian)
                    changed.append("guardian+")
                else:
                    if parts["relation"]:
                        match.relation = parts["relation"]
                    if parts["phone"]:
                        match.phone = parts["phone"]
                    changed.append("guardian")

        if changed:
            log_action(db, user, "dossier.import", "student", str(r.student_id), new_value=",".join(changed))
            updated += 1
    db.commit()
    return updated
