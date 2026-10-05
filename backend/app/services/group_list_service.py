"""«Список группы» для печати (.docx): таблица со столбцами, которые выбрал куратор.

Например, «ФИО + телефон + e-mail» — таблица из трёх столбцов (и необязательной нумерации). Документ собирается без
сторонних библиотек: минимальный .docx — это zip из нескольких XML-файлов (так же сделан лист ознакомления по
пропускам, `absence_sheet_service`). Поля — только обычные и контактные данные досье; особые категории (здоровье,
соц. статус, учёт) в список не входят вообще (152-ФЗ)."""
import datetime
import io
import re
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Student, StudentGuardian, StudentProfile, StudyGroup
from app.services import attendance_service

MAX_TITLE_LENGTH = 120

_FUNDING = {"budget": "Бюджет", "contract": "Договор"}
_STATUS = {"studying": "Учится", "academic_leave": "Академический отпуск", "expelled": "Отчислен"}


@dataclass(frozen=True)
class Field:
    key: str
    title: str  # заголовок столбца в документе
    weight: int  # относительная ширина столбца


# Порядок — тот же, в каком поля показываются в окне выбора.
FIELDS: tuple[Field, ...] = (
    Field("full_name", "ФИО", 3200),
    Field("birth_date", "Дата рождения", 1500),
    Field("phone", "Телефон", 1800),
    Field("email", "E-mail", 2800),
    Field("messenger", "Мессенджер", 1800),
    Field("registration_address", "Адрес регистрации", 3500),
    Field("residence_address", "Адрес проживания", 3500),
    Field("guardians", "Представители", 3200),
    Field("guardian_phones", "Телефоны представителей", 1900),
    Field("funding", "Бюджет / договор", 1400),
    Field("additional_education", "Доп. образование", 3000),
    Field("status", "Статус", 1600),
    Field("enrolled_at", "Зачислен", 1500),
    Field("signature", "Подпись", 2000),
    Field("note", "Примечание", 2500),
)
FIELDS_BY_KEY = {f.key: f for f in FIELDS}
NUMBER_COLUMN = Field("number", "№", 500)

_PROFILE_KEYS = {"birth_date", "phone", "email", "messenger", "registration_address", "residence_address", "additional_education", "funding"}
_WIDE_KEYS = {"registration_address", "residence_address", "additional_education"}

_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


class UnknownField(ValueError):
    pass


def parse_fields(raw: str) -> list[Field]:
    """«full_name,phone,email» → поля в том порядке, в каком их выбрали, без повторов."""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise UnknownField("Выберите хотя бы один столбец")
    unknown = [k for k in keys if k not in FIELDS_BY_KEY]
    if unknown:
        raise UnknownField(f"Неизвестные столбцы: {', '.join(unknown)}")
    seen: set[str] = set()
    result = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            result.append(FIELDS_BY_KEY[key])
    return result


def _date(value: datetime.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def collect_rows(db: Session, group: StudyGroup, on_date: datetime.date, fields: list[Field]) -> list[dict[str, str]]:
    """Студенты группы на дату (по алфавиту) и значения выбранных полей. Досье и представители — по одному
    запросу на всю группу, а не на каждого студента."""
    students = attendance_service.get_active_students(db, group.id, on_date)
    ids = [s.id for s in students]
    needs_profile = any(f.key in _PROFILE_KEYS for f in fields)
    needs_guardians = any(f.key in ("guardians", "guardian_phones") for f in fields)

    profiles: dict[int, StudentProfile] = {}
    if needs_profile and ids:
        profiles = {p.student_id: p for p in db.execute(select(StudentProfile).where(StudentProfile.student_id.in_(ids))).scalars()}
    guardians: dict[int, list[StudentGuardian]] = {}
    if needs_guardians and ids:
        rows = db.execute(
            select(StudentGuardian).where(StudentGuardian.student_id.in_(ids)).order_by(StudentGuardian.is_primary.desc(), StudentGuardian.id)
        ).scalars()
        for g in rows:
            guardians.setdefault(g.student_id, []).append(g)

    def value(student: Student, field: Field) -> str:
        profile = profiles.get(student.id)
        match field.key:
            case "full_name":
                return student.full_name
            case "birth_date":
                return _date(profile.birth_date) if profile else ""
            case "phone" | "email" | "messenger" | "registration_address" | "residence_address" | "additional_education":
                return (getattr(profile, field.key) or "") if profile else ""
            case "funding":
                return _FUNDING.get(profile.funding, "") if profile and profile.funding else ""
            case "guardians":
                return "\n".join(f"{g.full_name} ({g.relation})" for g in guardians.get(student.id, []))
            case "guardian_phones":
                return "\n".join(g.phone or "—" for g in guardians.get(student.id, []))
            case "status":
                return _STATUS.get(student.status.value, student.status.value)
            case "enrolled_at":
                return _date(student.enrolled_at)
            case _:  # «Подпись», «Примечание» — пустые столбцы для заполнения от руки
                return ""

    return [{f.key: value(s, f) for f in fields} for s in students]


# ---------- сборка .docx ----------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
_DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
_FONT = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>'
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    f"<w:docDefaults><w:rPrDefault><w:rPr>{_FONT}<w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:lang w:val=\"ru-RU\"/></w:rPr></w:rPrDefault>"
    '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    "</w:styles>"
)
_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

# Поля страницы A4, twips (1 см = 567): 2 см по бокам и 1,5 см сверху и снизу.
_PORTRAIT = (11906, 16838)
_MARGIN_SIDE, _MARGIN_TOP = 1134, 850


def _text(value: str) -> str:
    return escape(_INVALID_XML.sub("", value))


def _runs(value: str, size: int, bold: bool = False) -> str:
    """Текст ячейки: переводы строк — настоящие переносы Word (`w:br`)."""
    props = f"<w:rPr>{'<w:b/>' if bold else ''}<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/></w:rPr>"
    parts = []
    for i, line in enumerate(value.split("\n")):
        if i:
            parts.append(f"<w:r>{props}<w:br/></w:r>")
        if line:
            parts.append(f'<w:r>{props}<w:t xml:space="preserve">{_text(line)}</w:t></w:r>')
    return "".join(parts)


def _paragraph(value: str, size: int, bold: bool = False, center: bool = False, after: int = 0) -> str:
    jc = '<w:jc w:val="center"/>' if center else ""
    return f'<w:p><w:pPr><w:spacing w:after="{after}"/>{jc}</w:pPr>{_runs(value, size, bold)}</w:p>'


def _cell(width: int, value: str, size: int, bold: bool = False, center: bool = False, shade: bool = False) -> str:
    shading = '<w:shd w:val="clear" w:color="auto" w:fill="E7E6E6"/>' if shade else ""
    jc = '<w:jc w:val="center"/>' if center else ""
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shading}<w:vAlign w:val="center"/></w:tcPr>'
        f'<w:p><w:pPr><w:spacing w:before="40" w:after="40"/>{jc}</w:pPr>{_runs(value, size, bold)}</w:p></w:tc>'
    )


def column_widths(columns: list[Field], total: int) -> list[int]:
    """Ширины столбцов по весам так, чтобы вместе они были ровно шириной страницы."""
    weights = [c.weight for c in columns]
    widths = [max(400, round(total * w / sum(weights))) for w in weights]
    widths[-1] += total - sum(widths)  # остаток округления — в последний столбец
    return widths


def build_docx(
    group_code: str, department_name: str, curator_name: str | None, on_date: datetime.date,
    fields: list[Field], rows: list[dict[str, str]], numbering: bool = True, title: str | None = None,
) -> bytes:
    columns = ([NUMBER_COLUMN] if numbering else []) + fields
    # Узкая таблица — книжная страница, широкая — альбомная; чем больше столбцов, тем мельче шрифт.
    landscape = len(fields) >= 5 or (len(fields) >= 3 and any(f.key in _WIDE_KEYS for f in fields))
    page_w, page_h = _PORTRAIT[::-1] if landscape else _PORTRAIT
    text_width = page_w - 2 * _MARGIN_SIDE
    size = 24 if len(columns) <= 4 else 22 if len(columns) <= 6 else 20
    widths = column_widths(columns, text_width)

    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    header = (
        "<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>"
        + "".join(_cell(w, c.title, size, bold=True, center=True, shade=True) for c, w in zip(columns, widths))
        + "</w:tr>"
    )
    body = []
    for number, row in enumerate(rows, start=1):
        cells = []
        for column, width in zip(columns, widths):
            if column is NUMBER_COLUMN:
                cells.append(_cell(width, str(number), size, center=True))
            else:
                cells.append(_cell(width, row[column.key], size))
        body.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>" + "".join(cells) + "</w:tr>")

    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    table = (
        f'<w:tbl><w:tblPr><w:tblW w:w="{text_width}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
        '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        f"<w:tblGrid>{grid}</w:tblGrid>{header}{''.join(body)}</w:tbl>"
    )

    heading = (title or f"Список группы {group_code}").strip()
    details = [department_name]
    if curator_name:
        details.append(f"куратор: {curator_name}")
    details.append(f"на {on_date.strftime('%d.%m.%Y')}")
    details.append(f"студентов: {len(rows)}")
    orient = ' w:orient="landscape"' if landscape else ""
    section = (
        f'<w:sectPr><w:pgSz w:w="{page_w}" w:h="{page_h}"{orient}/>'
        f'<w:pgMar w:top="{_MARGIN_TOP}" w:right="{_MARGIN_SIDE}" w:bottom="{_MARGIN_TOP}" w:left="{_MARGIN_SIDE}" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_NS}><w:body>"
        f"{_paragraph(heading, 28, bold=True, center=True, after=60)}"
        f"{_paragraph(' · '.join(details), 22, center=True, after=200)}"
        f"{table}{section}</w:body></w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _RELS)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", _DOCUMENT_RELS)
        archive.writestr("word/styles.xml", _STYLES)
    return buffer.getvalue()
