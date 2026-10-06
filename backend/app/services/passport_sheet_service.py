"""«Социальный паспорт учебной группы» в Word — по образцу колледжа (`app/templates/social_passport.docx`).

Электронный паспорт в платформе ведётся из досье (см. `passport_service`); этот модуль только выгружает его в
образец: шапка, шрифты, поля, девять направлений профиля и их порядок берутся из образца как есть, подставляются
код группы, учебный год и студенты по направлениям. Подписи (куратор, соц. педагог, зав. отделением) остаются
строками для росписи.

Особые категории досье читаются только здесь и только для направлений образца: ОВЗ, учёт ПДН/КДН, внутренний
учёт, стипендия и здоровье в документ не попадают. Работа идёт на уровне XML образца (как `absence_sheet_service`),
каждая подстановка проверяет, что нужное место найдено, — иначе `TemplateMismatch`, а не испорченный документ."""
import datetime
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from app.core import field_crypto
from app.models import Student, StudentGuardian, StudentProfile, StudyGroup
from app.schemas.dossier import SpecialData
from app.services import passport_service

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "social_passport.docx"

# Направления профиля в порядке образца: (начало подписи в образце, проверка по особым данным).
# Сироты в образце отдельной строки не имеют — их вносят в «Студенты, находящиеся под опекой».
DIRECTIONS: list[tuple[str, callable]] = [
    ("Многодетные семьи", lambda s: s.large_family),
    ("Неполные семьи (потеря", lambda s: s.incomplete_family == "loss"),
    ("Неполные семьи (родители в разводе", lambda s: s.incomplete_family == "divorce"),
    ("Неполные семьи (матери-одиночки", lambda s: s.incomplete_family == "single_mother"),
    ("Малообеспеченные семьи", lambda s: s.low_income),
    ("Неблагополучные семьи", lambda s: s.dysfunctional_family),
    ("Студенты-инвалиды", lambda s: bool(s.disability_group)),
    ("Студенты , находящиеся под опекой", lambda s: s.under_guardianship or s.is_orphan),
    ("Дети из семей родителей- инвалидов", lambda s: s.parent_disabled),
]
MIN_ROWS = 2  # пустое направление остаётся с парой пустых строк — дописать от руки

_RPR = (
    '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:spacing w:val="2"/>'
    '<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
)


class TemplateMismatch(RuntimeError):
    """Образец документа не совпадает с тем, что ожидает сервис."""


class SpecialDataUnavailable(RuntimeError):
    """Нет ключа шифрования: направления профиля заполнить нечем."""


@dataclass
class SheetStudent:
    student_id: int
    name: str
    birth_date: datetime.date | None
    guardians: list[str]  # «ФИО (кем приходится)», основной представитель первым
    contacts: list[str]  # адрес проживания (или регистрации), телефон студента


def school_year(today: datetime.date) -> str:
    """Учебный год на дату: с сентября — этот и следующий, до августа — прошлый и этот."""
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start}-{start + 1}"


def collect(db: Session, group: StudyGroup, today: datetime.date) -> list[list[SheetStudent]]:
    """Студенты по направлениям образца (порядок — как в `DIRECTIONS`); студент с несколькими
    признаками попадает в каждое своё направление. Читает особые данные досье."""
    if not field_crypto.is_available():
        raise SpecialDataUnavailable
    students = passport_service.rosters(db, [group], today)[group.id]
    result: list[list[SheetStudent]] = [[] for _ in DIRECTIONS]
    if not students:
        return result
    ids = [s.id for s in students]
    profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(ids))}
    guardians: dict[int, list[StudentGuardian]] = {}
    for g in db.query(StudentGuardian).filter(StudentGuardian.student_id.in_(ids)).order_by(
        StudentGuardian.is_primary.desc(), StudentGuardian.id
    ):
        guardians.setdefault(g.student_id, []).append(g)

    for student in students:
        profile = profiles.get(student.id)
        if profile is None or not profile.special_enc:
            continue
        try:
            special = SpecialData(**field_crypto.decrypt_json(profile.special_enc))
        except field_crypto.EncryptionUnavailable:
            raise SpecialDataUnavailable
        flags = [test(special) for _, test in DIRECTIONS]
        if not any(flags):
            continue
        row = _student_row(student, profile, guardians.get(student.id, []))
        for index, hit in enumerate(flags):
            if hit:
                result[index].append(row)
    return result


def _student_row(student: Student, profile: StudentProfile, guardians: list[StudentGuardian]) -> SheetStudent:
    contacts = [a for a in (profile.residence_address or profile.registration_address,) if a]
    if profile.phone:
        contacts.append(profile.phone)
    return SheetStudent(
        student_id=student.id, name=student.full_name, birth_date=profile.birth_date,
        guardians=[f"{g.full_name} ({g.relation})" for g in guardians], contacts=contacts,
    )


def _replace_once(xml: str, old: str, new: str) -> str:
    if xml.count(old) != 1:
        raise TemplateMismatch(f"в образце паспорта не найден (или найден не один раз) фрагмент: {old[:70]!r}")
    return xml.replace(old, new)


def _strip_ids(xml: str) -> str:
    """Копии строк образца не должны повторять идентификаторы абзацев (w14:paraId/textId)."""
    return re.sub(r' w14:(?:paraId|textId)="[0-9A-Fa-f]+"', "", xml)


def _fill_cell(cell: str, lines: list[str], *, align: str) -> str:
    """Пустая ячейка образца → ячейка с текстом (каждая строка — через разрыв строки)."""
    if not lines:
        return cell
    runs = ""
    for i, text in enumerate(lines):
        runs += (
            f'<w:r>{_RPR.format(size=22)}{"<w:br/>" if i else ""}'
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
        )
    cell = cell.replace('<w:jc w:val="center"/>', f'<w:jc w:val="{align}"/>', 1)
    return cell.replace("</w:p></w:tc>", f"{runs}</w:p></w:tc>")


def _cells(row: str) -> list[str]:
    return re.findall(r"<w:tc>.*?</w:tc>", row, re.S)


def _data_row(template_row: str, student: SheetStudent | None) -> str:
    """Строка по образцу `template_row`, заполненная студентом (без студента — пустая, для росписи от руки)."""
    row = _strip_ids(template_row)
    if student is None:
        return row
    cells = _cells(row)
    fills = [
        (1, [student.name], "left"),
        (2, [student.birth_date.strftime("%d.%m.%Y")] if student.birth_date else [], "center"),
        (3, student.guardians, "left"),
        (4, student.contacts, "left"),
    ]
    for index, lines, align in fills:
        row = row.replace(cells[index], _fill_cell(cells[index], lines, align=align), 1)
    return row


def build_docx(*, group_code: str, today: datetime.date, directions: list[list[SheetStudent]]) -> bytes:
    with zipfile.ZipFile(TEMPLATE_PATH) as src:
        parts = {info.filename: src.read(info.filename) for info in src.infolist()}
        order = [info.filename for info in src.infolist()]
    xml = parts["word/document.xml"].decode("utf-8")

    xml = _replace_once(xml, "УЧЕБНОЙ ГРУППЫ ______", f"УЧЕБНОЙ ГРУППЫ {escape(group_code)}")
    xml = _replace_once(xml, "за 2026-2027 учебный год", f"за {school_year(today)} учебный год")

    if xml.count("<w:tbl>") != 1:
        raise TemplateMismatch("в образце паспорта ожидалась одна таблица")
    start = xml.index("<w:tbl>")
    end = xml.index("</w:tbl>") + len("</w:tbl>")
    table = xml[start:end]
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    first_row_at = table.index(rows[0])
    head, header_row, body = table[:first_row_at], rows[0], rows[1:]

    # Блоки направлений: строка с vMerge="restart" открывает направление, дальше — строки продолжения.
    blocks: list[list[str]] = []
    for row in body:
        if '<w:vMerge w:val="restart"/>' in _cells(row)[0]:
            blocks.append([row])
        elif blocks:
            blocks[-1].append(row)
    if len(blocks) != len(DIRECTIONS):
        raise TemplateMismatch(f"в образце паспорта ожидалось {len(DIRECTIONS)} направлений, найдено {len(blocks)}")

    out_rows = [header_row]
    for (title, _), block, students in zip(DIRECTIONS, blocks, directions, strict=True):
        label = re.sub(r"\s+", " ", "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", block[0])))
        if not label.replace(" ,", ",").startswith(title.replace(" ,", ",")):
            raise TemplateMismatch(f"направление образца {label[:40]!r} не совпадает с ожидаемым {title!r}")
        count = max(len(students), MIN_ROWS)
        first, blank = block[0], block[1]
        for i in range(count):
            student = students[i] if i < len(students) else None
            # Первая строка несёт подпись направления (объединённая ячейка образца), остальные — её продолжение.
            out_rows.append(_data_row(first if i == 0 else blank, student))
    xml = xml[:start] + head + "".join(out_rows) + "</w:tbl>" + xml[end:]

    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in order:
            dst.writestr(name, parts[name])
    return out.getvalue()
