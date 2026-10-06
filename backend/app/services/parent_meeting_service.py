"""Родительские собрания (этап 10): учёт собраний группы и «Протокол родительского собрания» в Word по образцу
колледжа (`app/templates/parent_meeting_protocol.docx`).

В протокол подставляются дата, номер, группа, куратор, повестка, сотрудники и спикеры, число родителей, формат
(подчёркивается «очный» или «дистанционный»), «слушали», «постановили» и регистрация родителей (ФИО из досье студентов).
Шапка, шрифты, места для подписи и таблица берутся из образца как есть; чего нет, остаётся чертой для записи от руки."""
import datetime
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import ParentMeeting, ParentMeetingAttendee, Student, StudentGuardian, StudyGroup
from app.services import docx_xml as dx
from app.services import group_event_service, passport_service
from app.services.docx_xml import TemplateMismatch

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "parent_meeting_protocol.docx"
FORMATS = ("in_person", "remote")
REGISTRATION_ROWS = 30  # строк регистрации в образце


def meetings_of(db: Session, group_id: int, year: str) -> list[ParentMeeting]:
    items = db.query(ParentMeeting).filter(ParentMeeting.study_group_id == group_id, ParentMeeting.school_year == year).all()
    return sorted(items, key=lambda m: (m.number, m.id))


def next_number(db: Session, group_id: int, year: str) -> int:
    numbers = [n for (n,) in db.query(ParentMeeting.number).filter(ParentMeeting.study_group_id == group_id, ParentMeeting.school_year == year)]
    return max(numbers, default=0) + 1


def attendee_ids(db: Session, meeting_ids: list[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {i: [] for i in meeting_ids}
    if meeting_ids:
        for row in db.query(ParentMeetingAttendee).filter(ParentMeetingAttendee.meeting_id.in_(meeting_ids)):
            result[row.meeting_id].append(row.guardian_id)
    return result


def group_guardians(db: Session, group: StudyGroup, today: datetime.date) -> list[tuple[StudentGuardian, Student]]:
    """Представители студентов, числящихся в группе сегодня: (представитель, студент) по фамилии студента."""
    students = passport_service.rosters(db, [group], today)[group.id]
    if not students:
        return []
    by_id = {s.id: s for s in students}
    rows = (
        db.query(StudentGuardian).filter(StudentGuardian.student_id.in_(list(by_id)))
        .order_by(StudentGuardian.is_primary.desc(), StudentGuardian.id).all()
    )
    pairs = [(g, by_id[g.student_id]) for g in rows]
    return sorted(pairs, key=lambda pair: (pair[1].last_name, pair[1].first_name, not pair[0].is_primary, pair[0].id))


def lines(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _numbered(xml: str, heading_startswith: str, items: list[str]) -> str:
    """Под заголовком — две строки образца «1…», «2…»: заменяются списком; без пунктов остаются как в образце."""
    if not items:
        return xml
    heading = dx.find(xml, heading_startswith)
    first = dx.next_paragraph(xml, heading)
    second = dx.next_paragraph(xml, first)
    if not (dx.plain(first).startswith("1") and dx.plain(second).startswith("2")):
        raise TemplateMismatch(f"под абзацем {heading_startswith[:40]!r} в образце ожидались строки «1…», «2…»")
    body = "".join(dx.rebuild_copy(second, dx.runs(f"{i}. {item}")) for i, item in enumerate(items, start=1))
    xml = dx.swap(xml, first, body)
    return dx.swap(xml, second, "")


def build_protocol_docx(
    *, meeting: ParentMeeting, group_code: str, curator_name: str | None, parents: list[str],
) -> bytes:
    """`parents` — ФИО присутствовавших родителей (из отметок); если их нет, берётся `meeting.parents_count`."""
    parts, order = dx.read_template(TEMPLATE_PATH)
    xml = parts["word/document.xml"].decode("utf-8")
    when = meeting.meeting_date

    xml = dx.rebuild(xml, dx.find(xml, "«___»"), dx.runs(dx.long_date(when) if when else "«___» __________ 20__ г."))
    title = dx.find(xml, "ПРОТОКОЛ РОДИТЕЛЬСКОГО СОБРАНИЯ")
    xml = dx.rebuild(xml, title, dx.runs(f"ПРОТОКОЛ РОДИТЕЛЬСКОГО СОБРАНИЯ №{meeting.number}", bold=True))
    xml = dx.rebuild(xml, dx.find(xml, "Группа"), dx.runs("Группа ") + dx.runs([(group_code, True)]))
    if curator_name:
        xml = dx.rebuild(xml, dx.find(xml, "Куратор группы"), dx.runs("Куратор группы ") + dx.runs([(curator_name, True)]))

    xml = _numbered(xml, "Повестка родительского собрания", lines(meeting.agenda))
    count = len(parents) if parents else meeting.parents_count
    if count is not None:
        xml = dx.rebuild(xml, dx.find(xml, "Присутствовало количество родителей"),
                         dx.runs("Присутствовало количество родителей/законных представителей: " + str(count)))
    xml = _numbered(xml, "Присутствовали сотрудники", lines(meeting.staff))
    xml = _numbered(xml, "Присутствовали приглашенные", lines(meeting.speakers))

    in_person = meeting.meeting_format == "in_person"
    xml = dx.rebuild(xml, dx.find(xml, "Формат проведения родительского собрания"),
                     dx.runs("Формат проведения родительского собрания", bold=True) + dx.runs(": ")
                     + dx.runs([("очный", in_person)]) + dx.runs(" / ") + dx.runs([("дистанционный", not in_person)]))

    for heading, text in (("СЛУШАЛИ", meeting.listened), ("ПОСТАНОВИЛИ", meeting.resolved)):
        if text:
            filler = dx.next_paragraph(xml, dx.find(xml, heading))
            if not dx.only_underscores(filler):
                raise TemplateMismatch(f"под заголовком {heading!r} в образце ожидалась строка из подчёркиваний")
            xml = dx.rebuild(xml, filler, dx.runs(text))

    # Регистрация родителей: строки образца 1–30; больше 30 — добавляются по образцу последней.
    start = xml.index("<w:tbl>")
    end = xml.index("</w:tbl>") + len("</w:tbl>")
    table = xml[start:end]
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    if len(rows) != REGISTRATION_ROWS + 1:
        raise TemplateMismatch(f"в образце протокола ожидалось {REGISTRATION_ROWS + 1} строк регистрации")
    head = table[: table.index(rows[0])]
    out = [rows[0]]
    for i in range(1, max(len(parents), REGISTRATION_ROWS) + 1):
        template = rows[i] if i <= REGISTRATION_ROWS else rows[-1].replace(f">{REGISTRATION_ROWS}<", f">{i}<", 1)
        row = dx.strip_ids(template)
        if i <= len(parents):
            cells = dx.cells_of(row)
            row = row.replace(cells[1], dx.fill_cell(cells[1], parents[i - 1], 24), 1)
            if when:
                row = row.replace(cells[2], dx.fill_cell(cells[2], when.strftime("%d.%m.%Y"), 24), 1)
        out.append(row)
    xml = xml[:start] + head + "".join(out) + "</w:tbl>" + xml[end:]
    return dx.write_docx(parts, order, dx.strip_ids(xml))


school_year = group_event_service.school_year
valid_school_year = group_event_service.valid_school_year
