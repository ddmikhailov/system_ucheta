"""План воспитательной работы группы и протокол классного часа (этап 9).

Мероприятия группы ведутся в платформе (раздел «План группы»), а по образцам колледжа выгружаются в Word:
  * «План воспитательной работы учебной группы» и «План воспитательной работы куратора» — один и тот же план
    (11 разделов бланка, пять столбцов), отличаются шапкой образца (у плана куратора — три подписи);
  * «Протокол классного часа» — из мероприятия с отметкой «классный час»: тема, формат и описание, присутствовавшие
    и лист присутствия.
Шапки, шрифты, поля и таблицы берутся из образцов (`app/templates/`) как есть, подставляются только данные платформы;
чего нет, остаётся чертой/пустой строкой для записи от руки."""
import datetime
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import GroupEvent, GroupEventAttendee, Student, StudyGroup
from app.services import docx_xml as dx
from app.services import passport_service
from app.services.docx_xml import TemplateMismatch

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# Разделы бланка плана — порядок и названия как в образце колледжа.
SECTIONS: list[tuple[str, str]] = [
    ("civic", "Гражданско - патриотическое воспитание"),
    ("legal", "Правовое воспитание, профилактика правонарушений"),
    ("cultural", "Культурно-эстетическое воспитание"),
    ("spiritual", "Духовно-нравственное воспитание"),
    ("sport", "Спортивно-оздоровительная работа и пропаганда здорового образа жизни"),
    ("professional", "Профессиональное воспитание (трудовое воспитание и работа по профориентации)"),
    ("psychology", "Совместная работа со специалистами социально-психологической службы"),
    ("parents", "Работа с родителями"),
    ("group_org", "Организационные мероприятия в группе"),
    ("college", "Организационные общеколледжные мероприятия"),
    ("career", "Профориентационные мероприятия"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]
STATUSES = ("planned", "done", "cancelled")
MIN_ROWS = 2  # в разделе без мероприятий остаются две пустые строки — дописать от руки (как в образце)
PROTOCOL_ROWS = 30  # строк листа присутствия в образце протокола


def school_year(day: datetime.date) -> str:
    """Учебный год на дату: с сентября — этот и следующий, до августа — прошлый и этот («2026-2027»)."""
    start = day.year if day.month >= 9 else day.year - 1
    return f"{start}-{start + 1}"


def valid_school_year(value: str) -> bool:
    m = re.fullmatch(r"(\d{4})-(\d{4})", value)
    return bool(m) and int(m.group(2)) == int(m.group(1)) + 1


def events_of(db: Session, group_id: int, year: str) -> list[GroupEvent]:
    """Мероприятия группы за учебный год: по дате, без даты — в конце."""
    items = db.query(GroupEvent).filter(GroupEvent.study_group_id == group_id, GroupEvent.school_year == year).all()
    return sorted(items, key=lambda e: (e.event_date is None, e.event_date or datetime.date.max, e.id))


def attendee_ids(db: Session, event_ids: list[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {i: [] for i in event_ids}
    if event_ids:
        for row in db.query(GroupEventAttendee).filter(GroupEventAttendee.event_id.in_(event_ids)):
            result[row.event_id].append(row.student_id)
    return result


def roster(db: Session, group: StudyGroup, today: datetime.date) -> list[Student]:
    return passport_service.rosters(db, [group], today)[group.id]


# ───────────────────────────── план (Word) ─────────────────────────────

def _result_text(event: GroupEvent) -> str:
    if event.status == "cancelled":
        return "Отменено" + (f": {event.result}" if event.result else "")
    if event.status == "done":
        return event.result or "Проведено"
    return ""


def _date_text(event: GroupEvent) -> str:
    parts = [event.event_date.strftime("%d.%m.%Y")] if event.event_date else []
    if event.time_text:
        parts.append(event.time_text)
    return "\n".join(parts)


def _event_row(blank_row: str, event: GroupEvent | None) -> str:
    row = dx.strip_ids(blank_row)
    if event is None:
        return row
    cells = dx.cells_of(row)
    values = [event.title, _date_text(event), event.responsible or "", event.goal or "", _result_text(event)]
    for cell, value in zip(cells, values, strict=True):
        row = row.replace(cell, dx.fill_cell(cell, value), 1)
    return row


def build_plan_docx(*, kind: str, group_code: str, year: str, events: list[GroupEvent]) -> bytes:
    """`kind`: «group» — план группы, «curator» — план куратора (образец с тремя подписями)."""
    if kind not in ("group", "curator"):
        raise ValueError(kind)
    parts, order = dx.read_template(TEMPLATES / ("group_plan.docx" if kind == "group" else "curator_plan.docx"))
    xml = parts["word/document.xml"].decode("utf-8")
    first, second = year.split("-")

    def retitle(startswith: str, text: str) -> None:
        nonlocal xml
        p = dx.find(xml, startswith)
        xml = dx.rebuild(xml, p, dx.runs(text, 24, bold=True))

    if kind == "group":
        retitle("План воспитательной работы учебной группы", f"План воспитательной работы учебной группы {group_code}")
        retitle("на 202", f"на {first} – {second} учебный год")
    else:
        retitle("2026/2027", f"{first}/{second} УЧЕБНОГО ГОДА")
        retitle("______________УЧЕБНОЙ ГРУППЫ", f"{group_code} УЧЕБНОЙ ГРУППЫ")

    start = xml.index("<w:tbl>")
    end = xml.index("</w:tbl>") + len("</w:tbl>")
    table = xml[start:end]
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    head = table[: table.index(rows[0])]
    body = rows[1:]
    headings = [i for i, r in enumerate(body) if "<w:gridSpan" in r]
    if len(headings) != len(SECTIONS):
        raise TemplateMismatch(f"в образце плана ожидалось {len(SECTIONS)} разделов, найдено {len(headings)}")

    by_section: dict[str, list[GroupEvent]] = {k: [] for k in SECTION_KEYS}
    for e in events:
        by_section.get(e.section, []).append(e)

    out = [rows[0]]
    for n, ((key, title), at) in enumerate(zip(SECTIONS, headings, strict=True)):
        label = re.sub(r"\s+", " ", dx.plain(body[at])).strip()
        if label != title:
            raise TemplateMismatch(f"раздел образца {label[:40]!r} не совпадает с ожидаемым {title!r}")
        out.append(dx.strip_ids(body[at]))
        blank = body[at + 1]
        items = by_section[key]
        for i in range(max(len(items), MIN_ROWS)):
            out.append(_event_row(blank, items[i] if i < len(items) else None))
    xml = xml[:start] + head + "".join(out) + "</w:tbl>" + xml[end:]
    return dx.write_docx(parts, order, dx.strip_ids(xml))


# ───────────────────────────── протокол классного часа (Word) ─────────────────────────────

def build_protocol_docx(
    *, event: GroupEvent, group_code: str, curator_name: str | None, listed: int, present: list[str],
) -> bytes:
    """`listed` — списочное число студентов группы, `present` — ФИО присутствовавших (по алфавиту)."""
    parts, order = dx.read_template(TEMPLATES / "class_hour_protocol.docx")
    xml = parts["word/document.xml"].decode("utf-8")
    when = event.event_date or datetime.date.today()

    date_p = dx.find(xml, "«___»")
    xml = dx.rebuild(xml, date_p, dx.runs(dx.long_date(when)))

    group_p = dx.find(xml, "Группа")
    xml = dx.rebuild(xml, group_p, dx.runs("Группа ") + dx.runs([(group_code, True)]))
    if curator_name:
        curator_p = dx.find(xml, "Куратор группы")
        xml = dx.rebuild(xml, curator_p, dx.runs("Куратор группы ") + dx.runs([(curator_name, True)]))

    topic_p = dx.find(xml, "Тема классного часа")
    continuation = dx.next_paragraph(xml, topic_p)
    xml = dx.rebuild(xml, topic_p, dx.runs("Тема классного часа", bold=True) + dx.runs(": " + event.title))
    if dx.only_underscores(continuation):
        xml = dx.swap(xml, continuation, "")

    count_p = dx.find(xml, "Присутствовало обучающихся")
    shown = str(len(present)) if present else "_________"
    xml = dx.rebuild(xml, count_p, dx.runs("Присутствовало обучающихся", bold=True)
                     + dx.runs(f": {shown} из списочного количества {listed}"))

    format_p = dx.find(xml, "Формат и описание проведения")
    if event.description:
        first_line = dx.next_paragraph(xml, format_p)
        second_line = dx.next_paragraph(xml, first_line)
        xml = dx.rebuild(xml, format_p, dx.runs("Формат и описание проведения классного часа", bold=True)
                         + dx.runs(": " + event.description))
        for line in (first_line, second_line):
            if dx.only_underscores(line):
                xml = dx.swap(xml, line, "")

    # Лист присутствия: строки образца 1–30 с ФИО и датой; больше 30 — добавляются строки по образцу последней.
    start = xml.index("<w:tbl>")
    end = xml.index("</w:tbl>") + len("</w:tbl>")
    table = xml[start:end]
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    if len(rows) != PROTOCOL_ROWS + 1:
        raise TemplateMismatch(f"в образце протокола ожидалось {PROTOCOL_ROWS + 1} строк листа присутствия")
    head = table[: table.index(rows[0])]
    out = [rows[0]]
    total = max(len(present), PROTOCOL_ROWS)
    for i in range(1, total + 1):
        template = rows[i] if i <= PROTOCOL_ROWS else rows[-1].replace(f">{PROTOCOL_ROWS}<", f">{i}<", 1)
        row = dx.strip_ids(template)
        if i <= len(present):
            cells = dx.cells_of(row)
            row = row.replace(cells[1], dx.fill_cell(cells[1], present[i - 1], 24), 1)
            row = row.replace(cells[2], dx.fill_cell(cells[2], when.strftime("%d.%m.%Y"), 24), 1)
        out.append(row)
    xml = xml[:start] + head + "".join(out) + "</w:tbl>" + xml[end:]
    return dx.write_docx(parts, order, dx.strip_ids(xml))
