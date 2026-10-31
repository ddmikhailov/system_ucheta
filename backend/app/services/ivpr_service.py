"""Копия плана ИВПР для студентов на внутреннем учёте (п. 5.1.11 положения о кураторе).

Отдельного «плана ИВПР» в платформе нет: ведётся журнал индивидуальной работы. Документ собирает из него по каждому
студенту группы, стоящему на внутреннем учёте (признак — в зашифрованном блоке досье), таблицу «дата · вид · цель ·
результат · следующий шаг». Строки таблицы дописываются от руки, подписи остаются под чертой. Признак «внутренний
учёт» — особые данные, поэтому выгрузка пишется в журнал просмотров досье (как соц. паспорт), а без ключа
шифрования недоступна."""
import datetime
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core import field_crypto
from app.models import StudentNote, StudentProfile, StudyGroup
from app.schemas.dossier import SpecialData
from app.services import individual_work_service, passport_service
from app.services.group_list_service import _NS, _MARGIN_SIDE, _MARGIN_TOP, _PORTRAIT, _cell, _paragraph, pack_docx

KIND_TITLES = {
    "conversation": "Беседа",
    "call": "Звонок",
    "parent_invited": "Вызов родителей",
    "prevention_council": "Совет профилактики",
    "home_visit": "Визит домой",
    "agreement": "Договорённость",
}
MIN_ROWS = 3  # пустые строки в конце таблицы студента — дописать от руки
_COLUMNS = (("Дата", 1300), ("Вид", 1700), ("Цель", 2400), ("Результат", 2400), ("Следующий шаг", 1700))


class SpecialDataUnavailable(RuntimeError):
    """Нет ключа шифрования: признак внутреннего учёта прочитать нечем."""


@dataclass
class IvprStudent:
    student_id: int
    name: str
    birth_date: datetime.date | None
    notes: list[StudentNote]


def collect(db: Session, group: StudyGroup, today: datetime.date) -> list[IvprStudent]:
    """Студенты группы на внутреннем учёте и их записи индивидуальной работы (старые — выше). Читает особые данные."""
    if not field_crypto.is_available():
        raise SpecialDataUnavailable
    students = passport_service.rosters(db, [group], today)[group.id]
    if not students:
        return []
    ids = [s.id for s in students]
    profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(ids))}
    chosen = []
    for student in students:
        profile = profiles.get(student.id)
        if profile is None or not profile.special_enc:
            continue
        try:
            special = SpecialData(**field_crypto.decrypt_json(profile.special_enc))
        except field_crypto.EncryptionUnavailable:
            raise SpecialDataUnavailable
        if special.internal_record:
            chosen.append((student, profile))
    notes: dict[int, list[StudentNote]] = {}
    for note in db.query(StudentNote).filter(
        StudentNote.student_id.in_([s.id for s, _ in chosen]), StudentNote.kind.in_(individual_work_service.WORK_KINDS)
    ):
        notes.setdefault(note.student_id, []).append(note)
    return [
        IvprStudent(
            student_id=s.id, name=s.full_name, birth_date=p.birth_date,
            notes=sorted(notes.get(s.id, []), key=individual_work_service.note_date),
        )
        for s, p in chosen
    ]


def _date(value: datetime.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _table(notes: list[StudentNote], text_width: int) -> str:
    total = sum(w for _, w in _COLUMNS)
    widths = [round(text_width * w / total) for _, w in _COLUMNS]
    widths[-1] += text_width - sum(widths)
    size = 20
    header = (
        "<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>"
        + "".join(_cell(w, title, size, bold=True, center=True, shade=True) for (title, _), w in zip(_COLUMNS, widths))
        + "</w:tr>"
    )
    rows = []
    for note in notes:
        values = [
            _date(individual_work_service.note_date(note)), KIND_TITLES.get(note.kind, note.kind),
            note.goal or "", note.result or "", _date(note.follow_up_on),
        ]
        rows.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>" + "".join(_cell(w, v, size) for v, w in zip(values, widths)) + "</w:tr>")
    for _ in range(max(0, MIN_ROWS - len(notes))):
        rows.append(
            '<w:tr><w:trPr><w:cantSplit/><w:trHeight w:val="500"/></w:trPr>'
            + "".join(_cell(w, "", size) for w in widths) + "</w:tr>"
        )
    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    return (
        f'<w:tbl><w:tblPr><w:tblW w:w="{text_width}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
        '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        f"<w:tblGrid>{grid}</w:tblGrid>{header}{''.join(rows)}</w:tbl>"
    )


def build_docx(group_code: str, curator_name: str | None, on_date: datetime.date, students: list[IvprStudent]) -> bytes:
    page_w, page_h = _PORTRAIT
    text_width = page_w - 2 * _MARGIN_SIDE
    body = [
        _paragraph("Копия плана ИВПР", 28, bold=True, center=True, after=60),
        _paragraph(
            f"Группа {group_code} · на {on_date.strftime('%d.%m.%Y')} · студентов на внутреннем учёте: {len(students)}",
            22, center=True, after=200,
        ),
    ]
    if not students:
        body.append(_paragraph("В группе нет студентов на внутреннем учёте.", 24, after=200))
    for student in students:
        born = f", дата рождения {_date(student.birth_date)}" if student.birth_date else ""
        body.append(_paragraph(f"{student.name}{born}", 24, bold=True, after=80))
        body.append(_table(student.notes, text_width))
        body.append(_paragraph("", 20, after=200))
    body.append(_paragraph(f"Куратор: {curator_name or '____________________'}  ____________  «___» ____________ 20__ г.", 22, after=0))
    section = (
        f'<w:sectPr><w:pgSz w:w="{page_w}" w:h="{page_h}"/>'
        f'<w:pgMar w:top="{_MARGIN_TOP}" w:right="{_MARGIN_SIDE}" w:bottom="{_MARGIN_TOP}" w:left="{_MARGIN_SIDE}" '
        'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
    )
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>{"".join(body)}{section}</w:body></w:document>'
    return pack_docx(document)
