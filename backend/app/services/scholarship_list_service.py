"""Список группы на стипендии (п. 5.1.14 положения о кураторе): студенты, у которых в досье указана стипендия,
сгруппированные по её виду. Выгрузка в Excel и в простую таблицу Word (образца колледжа для списка нет).

Поле «Стипендия» в досье — свободный текст из зашифрованного блока, поэтому виды сравниваются по тексту без учёта
регистра и лишних пробелов; в списке виден написанный первым вариант. Читает особые данные, так что вызывающий
пишет в журнал просмотров досье запись на каждого студента из списка (как выгрузка паспорта)."""
import datetime
import io
import zipfile
from dataclasses import dataclass, field

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy.orm import Session

from app.core import field_crypto
from app.core.xlsx import append_row
from app.models import StudentProfile, StudyGroup
from app.schemas.dossier import SpecialData
from app.services import docx_xml, passport_service
from app.services.passport_sheet_service import SpecialDataUnavailable

__all__ = ["SpecialDataUnavailable", "Kind", "collect", "build_xlsx", "build_docx", "student_ids"]


@dataclass
class Kind:
    title: str  # вид стипендии так, как его вписали в досье
    names: list[str] = field(default_factory=list)  # ФИО по алфавиту
    student_ids: list[int] = field(default_factory=list)


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def collect(db: Session, group: StudyGroup, today: datetime.date) -> list[Kind]:
    """Виды стипендии группы: сначала самые многочисленные, при равенстве — по алфавиту названия."""
    if not field_crypto.is_available():
        raise SpecialDataUnavailable
    students = passport_service.rosters(db, [group], today)[group.id]
    if not students:
        return []
    profiles = {
        p.student_id: p
        for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_([s.id for s in students]))
    }
    kinds: dict[str, Kind] = {}
    for student in students:  # состав уже отсортирован по фамилии и имени
        profile = profiles.get(student.id)
        if profile is None or not profile.special_enc:
            continue
        try:
            special = SpecialData(**field_crypto.decrypt_json(profile.special_enc))
        except field_crypto.EncryptionUnavailable:
            raise SpecialDataUnavailable
        title = " ".join((special.scholarship or "").split())
        if not title:
            continue
        kind = kinds.setdefault(_key(title), Kind(title=title))
        kind.names.append(student.full_name)
        kind.student_ids.append(student.id)
    return sorted(kinds.values(), key=lambda k: (-len(k.names), _key(k.title)))


def student_ids(kinds: list[Kind]) -> list[int]:
    return sorted({sid for k in kinds for sid in k.student_ids})


def build_xlsx(group: StudyGroup, today: datetime.date, kinds: list[Kind]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Стипендии"
    ws.append([f"Список группы {group.code} на стипендии на {today.strftime('%d.%m.%Y')}"])
    ws["A1"].font = Font(bold=True)
    ws.append([])
    ws.append(["№", "ФИО", "Вид стипендии"])
    for cell in ws[3]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    number = 0
    for kind in kinds:
        for name in kind.names:
            number += 1
            append_row(ws, [number, name, kind.title])
    if not number:
        ws.append(["", "В группе нет студентов со стипендией", ""])
    else:
        ws.append([])
        ws.append(["", "Итого", number])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
        for kind in kinds:
            append_row(ws, ["", f"{kind.title}", len(kind.names)])
    ws.freeze_panes = "A4"
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 32
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_BORDERS = "".join(
    f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
    for side in ("top", "left", "bottom", "right", "insideH", "insideV")
)
_WIDTHS = (700, 5600, 3300)  # №, ФИО, вид стипендии (twips, вместе — ширина страницы с полями)


def _paragraph(text: str, *, size: int = 24, bold: bool = False, center: bool = False, after: int = 120) -> str:
    jc = '<w:jc w:val="center"/>' if center else ""
    return (
        f'<w:p><w:pPr><w:spacing w:after="{after}"/>{jc}</w:pPr>'
        f"{docx_xml.runs(text, size, bold=bold)}</w:p>"
    )


def _row(cells: list[str], *, bold: bool = False) -> str:
    out = []
    for width, text in zip(_WIDTHS, cells):
        out.append(
            f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
            f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>{docx_xml.runs(text, 24, bold=bold) if text else ""}</w:p></w:tc>'
        )
    return f'<w:tr><w:trPr><w:cantSplit/></w:trPr>{"".join(out)}</w:tr>'


def build_docx(group: StudyGroup, today: datetime.date, kinds: list[Kind]) -> bytes:
    """Простая таблица Word: шапка (колледж, группа, дата), строки «№ — ФИО — вид стипендии», итоги по видам."""
    rows = [_row(["№", "ФИО", "Вид стипендии"], bold=True)]
    number = 0
    for kind in kinds:
        for name in kind.names:
            number += 1
            rows.append(_row([str(number), name, kind.title]))
    if not number:
        rows.append(_row(["", "В группе нет студентов со стипендией", ""]))
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in _WIDTHS)
    table = (
        f'<w:tbl><w:tblPr><w:tblW w:w="{sum(_WIDTHS)}" w:type="dxa"/><w:tblBorders>{_BORDERS}</w:tblBorders>'
        f'<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(rows)}</w:tbl>'
    )
    body = [
        _paragraph("СПИСОК СТУДЕНТОВ НА СТИПЕНДИИ", bold=True, center=True),
        _paragraph(f"Группа {group.code}, по состоянию на {docx_xml.long_date(today)}", center=True, after=240),
        table,
        _paragraph("", after=120),
    ]
    if number:
        body.append(_paragraph(f"Всего: {number}", bold=True))
        body.extend(_paragraph(f"{kind.title}: {len(kind.names)}") for kind in kinds)
    body.append(_paragraph("", after=240))
    body.append(_paragraph("Куратор ____________________ / ____________________ /"))
    sect = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS}><w:body>{"".join(body)}{sect}</w:body></w:document>'
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>'
        ),
        "word/document.xml": document,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name, xml in parts.items():
            dst.writestr(name, xml.encode("utf-8"))
    return out.getvalue()

