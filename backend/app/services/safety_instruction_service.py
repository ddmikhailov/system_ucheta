"""Журнал инструктажа по охране труда (п. 5.1.15 положения): записи группы и печатный бланк для подписей.

Подпись на бумаге обязательна, поэтому платформа автоматизирует только печать: шапка записи (дата, вид, тема, кто
провёл) и таблица «№ · ФИО · Подпись» со всеми студентами группы на день печати. Бланк собирается тем же минимальным
.docx, что и «Список группы» (`group_list_service`); в него попадают только ФИО, без данных досье."""
import datetime

from sqlalchemy.orm import Session

from app.models import SafetyInstruction, StudyGroup
from app.services import attendance_service, group_event_service, group_list_service as gl

KINDS = {
    "introductory": "Вводный",
    "primary": "Первичный на рабочем месте",
    "repeated": "Повторный",
    "targeted": "Целевой",
    "unplanned": "Внеплановый",
}

school_year = group_event_service.school_year
valid_school_year = group_event_service.valid_school_year

_COLUMNS = (gl.NUMBER_COLUMN, gl.Field("full_name", "ФИО", 5200), gl.Field("signature", "Подпись", 3000), gl.Field("date", "Дата", 1500))


def records_of(db: Session, group_id: int, year: str) -> list[SafetyInstruction]:
    items = db.query(SafetyInstruction).filter(SafetyInstruction.study_group_id == group_id, SafetyInstruction.school_year == year).all()
    return sorted(items, key=lambda r: (r.instruction_date, r.id))


def build_blank_docx(*, record: SafetyInstruction, group_code: str, department_name: str, curator_name: str | None, students: list[str]) -> bytes:
    size = 24
    widths = gl.column_widths(list(_COLUMNS), gl._PORTRAIT[0] - 2 * gl._MARGIN_SIDE)
    text_width = sum(widths)
    header = (
        "<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>"
        + "".join(gl._cell(w, c.title, size, bold=True, center=True, shade=True) for c, w in zip(_COLUMNS, widths))
        + "</w:tr>"
    )
    body = "".join(
        "<w:tr><w:trPr><w:cantSplit/></w:trPr>"
        + gl._cell(widths[0], str(n), size, center=True) + gl._cell(widths[1], name, size)
        + gl._cell(widths[2], "", size) + gl._cell(widths[3], "", size)
        + "</w:tr>"
        for n, name in enumerate(students, start=1)
    )
    borders = "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>' for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
    table = (
        f'<w:tbl><w:tblPr><w:tblW w:w="{text_width}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
        '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        f'<w:tblGrid>{"".join(f"""<w:gridCol w:w="{w}"/>""" for w in widths)}</w:tblGrid>{header}{body}</w:tbl>'
    )
    lines = [
        f"Группа {group_code} · {department_name}",
        f"Дата инструктажа: {record.instruction_date.strftime('%d.%m.%Y')}",
        f"Вид инструктажа: {KINDS.get(record.kind, record.kind)}",
        f"Тема: {record.topic}",
        f"Инструктаж провёл: {record.conducted_by or curator_name or '____________________'}",
    ]
    if record.note:
        lines.append(f"Примечание: {record.note}")
    section = (
        f'<w:sectPr><w:pgSz w:w="{gl._PORTRAIT[0]}" w:h="{gl._PORTRAIT[1]}"/>'
        f'<w:pgMar w:top="{gl._MARGIN_TOP}" w:right="{gl._MARGIN_SIDE}" w:bottom="{gl._MARGIN_TOP}" w:left="{gl._MARGIN_SIDE}" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {gl._NS}><w:body>"
        + gl._paragraph("ЖУРНАЛ ИНСТРУКТАЖА ПО ОХРАНЕ ТРУДА", 28, bold=True, center=True, after=120)
        + "".join(gl._paragraph(line, 24, after=40) for line in lines)
        + gl._paragraph("", 24, after=120)
        + table
        + gl._paragraph("", 24, after=200)
        + gl._paragraph("Инструктаж провёл ______________________  (подпись, ФИО)", 24)
        + f"{section}</w:body></w:document>"
    )
    return gl.package_docx(document)
