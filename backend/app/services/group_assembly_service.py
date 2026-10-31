"""Общие собрания студентов группы и протокол в Word (п. 5.1.10 положения о кураторе).

Образца колледжа для протокола общего собрания нет, поэтому документ собирается так же, как «Список группы»
(`group_list_service`): заголовок, председатель и секретарь, число присутствовавших, повестка, «слушали / постановили»
и строки подписей. Чего куратор не внёс, остаётся чертой для записи от руки."""
import datetime

from sqlalchemy.orm import Session

from app.models import GroupAssembly
from app.services.group_list_service import _NS, _MARGIN_SIDE, _MARGIN_TOP, _PORTRAIT, _paragraph, pack_docx
from app.services.parent_meeting_service import lines

BLANK = "____________________"


def assemblies_of(db: Session, group_id: int, year: str) -> list[GroupAssembly]:
    items = db.query(GroupAssembly).filter(GroupAssembly.study_group_id == group_id, GroupAssembly.school_year == year).all()
    return sorted(items, key=lambda a: (a.number, a.id))


def next_number(db: Session, group_id: int, year: str) -> int:
    numbers = [n for (n,) in db.query(GroupAssembly.number).filter(GroupAssembly.study_group_id == group_id, GroupAssembly.school_year == year)]
    return max(numbers, default=0) + 1


def build_protocol_docx(*, assembly: GroupAssembly, group_code: str, listed: int, curator_name: str | None) -> bytes:
    """`listed` — сколько студентов числится в группе (для «присутствовало N из M»)."""
    page_w, page_h = _PORTRAIT
    when = assembly.assembly_date.strftime("%d.%m.%Y") if assembly.assembly_date else "«___» ____________ 20__ г."
    present = str(assembly.present_count) if assembly.present_count is not None else "____"
    agenda = lines(assembly.agenda)
    body = [
        _paragraph(f"ПРОТОКОЛ № {assembly.number}", 28, bold=True, center=True, after=60),
        _paragraph(f"общего собрания группы {group_code}", 26, center=True, after=60),
        _paragraph(f"от {when}", 24, center=True, after=240),
        _paragraph(f"Председатель: {assembly.chair or BLANK}", 24, after=60),
        _paragraph(f"Секретарь: {assembly.secretary or BLANK}", 24, after=60),
        _paragraph(f"Присутствовало: {present} из {listed} студентов группы", 24, after=240),
        _paragraph("ПОВЕСТКА ДНЯ:", 24, bold=True, after=60),
    ]
    body += [_paragraph(f"{i}. {item}", 24, after=40) for i, item in enumerate(agenda, start=1)] or [_paragraph(f"1. {BLANK}", 24, after=40)]
    body += [
        _paragraph("СЛУШАЛИ:", 24, bold=True, after=60),
        _paragraph(assembly.listened or f"{BLANK}\n{BLANK}", 24, after=200),
        _paragraph("ПОСТАНОВИЛИ:", 24, bold=True, after=60),
        _paragraph(assembly.resolved or f"{BLANK}\n{BLANK}", 24, after=360),
        _paragraph(f"Председатель собрания  ____________  {assembly.chair or BLANK}", 24, after=160),
        _paragraph(f"Секретарь  ____________  {assembly.secretary or BLANK}", 24, after=160),
        _paragraph(f"Куратор группы  ____________  {curator_name or BLANK}", 24, after=0),
    ]
    section = (
        f'<w:sectPr><w:pgSz w:w="{page_w}" w:h="{page_h}"/>'
        f'<w:pgMar w:top="{_MARGIN_TOP}" w:right="{_MARGIN_SIDE}" w:bottom="{_MARGIN_TOP}" w:left="{_MARGIN_SIDE}" '
        'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
    )
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>{"".join(body)}{section}</w:body></w:document>'
    return pack_docx(document)
