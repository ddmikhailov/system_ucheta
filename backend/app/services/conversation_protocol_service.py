"""«Протокол беседы» в Word — единый бланк колледжа (беседа с обучающимся или родителями).

Данные берутся из заметки журнала индивидуальной работы (беседа, вызов, приглашение родителей, договорённость):
дата, цель, присутствовавшие, содержание, итог. Шапка с логотипом колледжа и поля страницы остаются из
`app/templates/conversation_protocol.docx`, а само тело документа строится здесь на таблицах с ФИКСИРОВАННОЙ
раскладкой: ширины колонок заданы в документе и не зависят от введённого текста, длинное значение переносится
внутри своего поля (а не «расплывается» по странице), незаполненное остаётся линиями для записи от руки.
Подписи (должность / подпись / ФИО) — отдельные строки с подписями-пояснениями под чертой, строка не разрывается
между страницами."""
import datetime
import io
import math
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from app.models import StudentNote
from app.services.absence_sheet_service import MONTHS_GENITIVE

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "conversation_protocol.docx"
PROTOCOL_KINDS = ("conversation", "call", "parent_invited", "agreement")  # виды заметок, из которых делается протокол

_PARENT_WORDS = ("мать", "мама", "отец", "папа", "родител", "законн", "представител", "опекун", "бабушк", "дедушк")

PAGE_BOTTOM_TWIPS = 850        # поле снизу (в образце было 284 — текст упирался в край листа)
LABEL_WIDTH = 2600            # единая колонка подписей полей — значения всех полей начинаются с одного отступа
CONTENT_WIDTH = 9355           # A4 (11906) − поля слева 1701 и справа 850
_CHARS_PER_LINE = 52           # консервативная оценка знаков в строке для расчёта дополняющих линий


class TemplateMismatch(RuntimeError):
    """Образец документа (шапка с логотипом) не совпадает с тем, что ожидает сервис."""


def long_date(d: datetime.date) -> str:
    return f"«{d.day:02d}» {MONTHS_GENITIVE[d.month - 1]} {d.year} г."


def pick_form(note: StudentNote) -> str:
    """С кем беседа (для подзаголовка): вызов родителей или родитель/представитель среди присутствующих."""
    if note.kind == "parent_invited":
        return "parents"
    people = (note.participants or "").lower()
    return "parents" if any(word in people for word in _PARENT_WORDS) else "student"


# ---------- примитивы WordprocessingML ----------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(text: str) -> str:
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def _run(text: str, *, bold: bool = False, size: int = 24, caps: bool = False) -> str:
    rpr = (
        '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
        f'{"<w:b/><w:bCs/>" if bold else ""}{"<w:caps/>" if caps else ""}'
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    )
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(runs: str = "", *, jc: str = "left", before: int = 0, after: int = 0, keep_next: bool = False, size: int = 24) -> str:
    ppr = (
        f'{"<w:keepNext/>" if keep_next else ""}<w:spacing w:before="{before}" w:after="{after}" w:line="240" w:lineRule="auto"/>'
        f'<w:jc w:val="{jc}"/><w:rPr><w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
    )
    return f"<w:p><w:pPr>{ppr}</w:pPr>{runs}</w:p>"


def _cell(width: int, content: str, *, span: int = 1, bottom: bool = False, valign: str = "bottom") -> str:
    borders = '<w:tcBorders><w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/></w:tcBorders>' if bottom else ""
    grid_span = f'<w:gridSpan w:val="{span}"/>' if span > 1 else ""
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{grid_span}{borders}<w:vAlign w:val="{valign}"/></w:tcPr>'
        f'{content or _para()}</w:tc>'
    )


def _row(cells: str, *, height: int = 0, exact: bool = False) -> str:
    height_xml = f'<w:trHeight w:val="{height}" w:hRule="{"exact" if exact else "atLeast"}"/>' if height else ""
    return f"<w:tr><w:trPr><w:cantSplit/>{height_xml}</w:trPr>{cells}</w:tr>"


def _table(grid: list[int], rows: str) -> str:
    cols = "".join(f'<w:gridCol w:w="{w}"/>' for w in grid)
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
        '<w:tblCellMar><w:left w:w="40" w:type="dxa"/><w:right w:w="40" w:type="dxa"/></w:tblCellMar>'
        '<w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>%s</w:tblGrid>%s</w:tbl>' % (sum(grid), cols, rows)
    ) + _para(size=8)


def _lines(text: str, *, bold: bool = False, keep_next: bool = False) -> str:
    """Многострочный текст → абзацы внутри ячейки (длинные строки переносятся по ширине ячейки)."""
    parts = [line for line in _clean(text).split("\n")]
    return "".join(_para(_run(line, bold=bold) if line else "", keep_next=keep_next) for line in parts) or _para()


def _estimate_lines(text: str, chars: int = _CHARS_PER_LINE) -> int:
    return sum(max(1, math.ceil(len(line) / chars)) for line in _clean(text).split("\n")) if text else 0


# ---------- блоки бланка ----------

def _field(label: str, value: str | None, *, min_lines: int = 1, label_width: int = LABEL_WIDTH) -> str:
    """Поле «Подпись: значение» с линией под значением; если значение короткое — дописываются пустые линии
    для записи от руки (всего не меньше `min_lines`), если длинное — оно переносится внутри поля."""
    text = (value or "").strip()
    grid = [label_width, CONTENT_WIDTH - label_width]
    rows = _row(
        _cell(grid[0], _para(_run(label)), valign="top" if _estimate_lines(text, 40) > 1 else "bottom") + _cell(grid[1], _lines(text), bottom=True),
        height=400,
    )
    extra = max(0, min_lines - max(1, _estimate_lines(text, _CHARS_PER_LINE)))
    for _ in range(extra):
        rows += _row(_cell(CONTENT_WIDTH, _para(), span=2, bottom=True), height=400)
    return _table(grid, rows)


def _heading(label: str) -> str:
    """Подпись раздела без значения в той же строке («Слушали», «Решение»)."""
    return _para(_run(label), before=120, keep_next=True)


def _block(label: str, value: str | None, *, min_lines: int) -> str:
    """Раздел: подпись отдельной строкой, под ней текст в рамке линий (или пустые линии для рукописи)."""
    text = (value or "").strip()
    rows = _row(_cell(CONTENT_WIDTH, _lines(text), bottom=True), height=400)
    extra = max(0, min_lines - max(1, _estimate_lines(text, 62)))
    for _ in range(extra):
        rows += _row(_cell(CONTENT_WIDTH, _para(), bottom=True), height=400)
    return _heading(label) + _table([CONTENT_WIDTH], rows)


def _date_row(when: datetime.date) -> str:
    grid = [LABEL_WIDTH, 3300, CONTENT_WIDTH - LABEL_WIDTH - 3300]
    return _table(grid, _row(
        _cell(grid[0], _para(_run("Дата"))) + _cell(grid[1], _para(_run(long_date(when)), jc="center"), bottom=True) + _cell(grid[2], _para()),
        height=400,
    ))


def _signature_rows(count: int, *, first_position: str = "", first_name: str = "") -> str:
    """Строки «Должность / подпись / ФИО» с подписями-пояснениями под чертой."""
    grid = [2500, 160, 2000, 160, CONTENT_WIDTH - 4820]
    out = ""
    for i in range(count):
        position = first_position if i == 0 else ""
        name = first_name if i == 0 else ""
        keep = i < count - 1
        out += _row(
            _cell(grid[0], _para(_run(position), keep_next=True), bottom=True)
            + _cell(grid[1], _para(_run("/"), jc="center", keep_next=True))
            + _cell(grid[2], _para(keep_next=True), bottom=True)
            + _cell(grid[3], _para(_run("/"), jc="center", keep_next=True))
            + _cell(grid[4], _para(_run(name), keep_next=True), bottom=True),
            height=520,
        )
        caption = lambda t: _para(_run(t, size=16), jc="center", keep_next=keep, size=16)  # noqa: E731
        out += _row(
            _cell(grid[0], _para(size=16, keep_next=keep)) + _cell(grid[1], _para(size=16, keep_next=keep))
            + _cell(grid[2], caption("(подпись)"), valign="top") + _cell(grid[3], _para(size=16, keep_next=keep))
            + _cell(grid[4], caption("(ФИО)"), valign="top"),
        )
    return _table(grid, out)


def _acquainted_rows(count: int) -> str:
    grid = [3600, 160, CONTENT_WIDTH - 3760]
    out = ""
    for i in range(count):
        keep = i < count - 1
        out += _row(
            _cell(grid[0], _para(keep_next=True), bottom=True) + _cell(grid[1], _para(_run("/"), jc="center", keep_next=True))
            + _cell(grid[2], _para(keep_next=True), bottom=True),
            height=520,
        )
        out += _row(
            _cell(grid[0], _para(_run("(подпись)", size=16), jc="center", keep_next=keep, size=16), valign="top")
            + _cell(grid[1], _para(size=16, keep_next=keep))
            + _cell(grid[2], _para(_run("(ФИО)", size=16), jc="center", keep_next=keep, size=16), valign="top"),
        )
    return _table(grid, out)


def _people(note: StudentNote) -> str:
    people = [line.strip() for line in _clean(note.participants or "").split("\n") if line.strip()]
    return "\n".join(f"{i}. {person}" for i, person in enumerate(people, start=1))


def _title(subtitle: str) -> str:
    return (
        _para(_run("ПРОТОКОЛ БЕСЕДЫ", bold=True, size=28), jc="center", before=120, after=40, keep_next=True, size=28)
        + _para(_run(subtitle), jc="center", after=200, keep_next=True)
    )


def _body(note: StudentNote, when: datetime.date, student_name: str, group_code: str, curator: str | None) -> str:
    """Единый бланк: сверху — «Цель беседы» и «Тема обсуждения» (как в прежнем образце), ниже — форма нового
    протокола: решение, заявления, подписи участников и ознакомление законных представителей."""
    subtitle = "с родителями (законными представителями)" if pick_form(note) == "parents" else "с обучающимся"
    grid = [LABEL_WIDTH, 3600, 900, CONTENT_WIDTH - LABEL_WIDTH - 4500]
    who = _table(grid, _row(
        _cell(grid[0], _para(_run("Обучающийся")))
        + _cell(grid[1], _para(_run(student_name)), bottom=True)
        + _cell(grid[2], _para(_run("группа"), jc="center"))
        + _cell(grid[3], _para(_run(group_code), jc="center"), bottom=True),
        height=400,
    ))
    return (
        _title(subtitle)
        + _date_row(when)
        + who
        + _field("Куратор", curator)
        + _field("Присутствовали", _people(note), min_lines=3)
        + _block("Цель беседы", note.goal, min_lines=2)
        + _block("Тема обсуждения", note.text, min_lines=7)
        + _block("Решение", note.result, min_lines=4)
        + _field("Протокол прочитан", "")
        + _field("Заявления, замечания", "", min_lines=2)
        + _para(_run("Участники встречи:"), before=200, after=80, keep_next=True)
        + _signature_rows(3, first_position="Куратор", first_name=curator or "")
        + _para(_run("Законные представители ознакомлены:"), before=160, after=80, keep_next=True)
        + _acquainted_rows(2)
    )


def build_docx(
    *, note: StudentNote, student_name: str, group_code: str, curator_name: str | None,
) -> bytes:
    with zipfile.ZipFile(TEMPLATE_PATH) as src:
        parts = {info.filename: src.read(info.filename) for info in src.infolist()}
        order = [info.filename for info in src.infolist()]
    xml = parts["word/document.xml"].decode("utf-8")
    body_start = xml.index("<w:body>") + len("<w:body>")
    marker = xml.find("Дата проведения")
    if marker == -1 or "<w:drawing" not in xml[body_start:marker]:
        raise TemplateMismatch("в образце протокола не найдена шапка с логотипом колледжа")
    header = xml[body_start: xml.rindex("<w:p ", body_start, marker)]  # пустые абзацы + рисунок шапки из образца
    sect = re.search(r"<w:sectPr.*?</w:sectPr>", xml, re.S)
    if sect is None:
        raise TemplateMismatch("в образце протокола нет параметров страницы")
    sect_xml = re.sub(r'w:bottom="\d+"', f'w:bottom="{PAGE_BOTTOM_TWIPS}"', sect.group(0), count=1)

    when = note.occurred_on or note.created_at.date()
    body = _body(note, when, student_name, group_code, curator_name)

    parts["word/document.xml"] = (xml[: body_start] + header + body + sect_xml + xml[xml.index("</w:body>"):]).encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in order:
            dst.writestr(name, parts[name])
    return out.getvalue()
