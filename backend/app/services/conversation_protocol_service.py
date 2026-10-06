"""«Протокол беседы с обучающимся/родителем» в Word — по образцу колледжа (`app/templates/conversation_protocol.docx`).

Данные берутся из заметки журнала индивидуальной работы (беседа, вызов, приглашение родителей, договорённость):
дата, цель, присутствовавшие, содержание, итог. Шапка, шрифты, поля и места для подписей (рисованные линии
куратора и четырёх участников) остаются из образца как есть. Что не заполнено в заметке, остаётся чертой для
записи от руки. Работа идёт на уровне XML образца (как `absence_sheet_service`), каждая подстановка проверяет, что
нужное место найдено, — иначе `TemplateMismatch`, а не испорченный документ."""
import datetime
import io
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from app.models import StudentNote
from app.services.absence_sheet_service import MONTHS_GENITIVE

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "conversation_protocol.docx"
PROTOCOL_KINDS = ("conversation", "call", "parent_invited", "agreement")  # виды заметок, из которых делается протокол

_RPR = '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>{extra}<w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr>'


class TemplateMismatch(RuntimeError):
    """Образец документа не совпадает с тем, что ожидает сервис."""


def long_date(d: datetime.date) -> str:
    return f"«{d.day:02d}» {MONTHS_GENITIVE[d.month - 1]} {d.year} г."


def _runs(text: str, *, underline: bool = False) -> str:
    """Текст с переносами строк → прогоны образца (Times New Roman 14)."""
    rpr = _RPR.format(extra='<w:u w:val="single"/>' if underline else "")
    parts = []
    for i, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        parts.append(f'<w:r>{rpr}{"<w:br/>" if i else ""}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
    return "".join(parts)


def _paragraphs(xml: str) -> list[str]:
    return re.findall(r"<w:p[ >].*?</w:p>", xml[xml.index("<w:body>"):], re.S)


def _plain(paragraph: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", paragraph))


def _find(xml: str, startswith: str) -> str:
    found = [p for p in _paragraphs(xml) if _plain(p).startswith(startswith)]
    if len(found) != 1:
        raise TemplateMismatch(f"в образце протокола не найден (или найден не один раз) абзац: {startswith[:50]!r}")
    return found[0]


def _find_containing(xml: str, text: str) -> str:
    found = [p for p in _paragraphs(xml) if text in _plain(p)]
    if len(found) != 1:
        raise TemplateMismatch(f"в образце протокола не найден (или найден не один раз) абзац с текстом: {text!r}")
    return found[0]


def _swap(xml: str, old: str, new: str) -> str:
    if xml.count(old) != 1:
        raise TemplateMismatch(f"в образце протокола не найден (или найден не один раз) фрагмент: {old[:70]!r}")
    return xml.replace(old, new)


def _next(xml: str, paragraph: str) -> str:
    paragraphs = _paragraphs(xml)
    return paragraphs[paragraphs.index(paragraph) + 1]


def _only_underscores(paragraph: str) -> bool:
    return not _plain(paragraph).strip("_ ")


def _run_with(paragraph: str, text_prefix: str) -> str:
    """Единственный прогон абзаца, текст которого начинается с `text_prefix` (после необязательного пробела)."""
    runs = [r for r in re.findall(r"<w:r[ >].*?</w:r>", paragraph, re.S) if _plain(r).lstrip().startswith(text_prefix)]
    if len(runs) != 1:
        raise TemplateMismatch(f"в абзаце образца не найден прогон: {text_prefix!r}")
    return runs[0]


def build_docx(
    *, note: StudentNote, student_name: str, group_code: str, curator_name: str | None,
) -> bytes:
    with zipfile.ZipFile(TEMPLATE_PATH) as src:
        parts = {info.filename: src.read(info.filename) for info in src.infolist()}
        order = [info.filename for info in src.infolist()]
    xml = parts["word/document.xml"].decode("utf-8")
    when = note.occurred_on or note.created_at.date()

    # Дата: «___»______20__ г. — прогоны абзаца заменяются одной строкой с датой.
    date_p = _find(xml, "«__")
    head = date_p[: date_p.index("</w:pPr>") + len("</w:pPr>")]
    xml = _swap(xml, date_p, head + _runs(long_date(when)) + "</w:p>")

    for prefix, label, value in (
        ("ФИО обучающегося", "ФИО обучающегося ", student_name),
    ):
        p = _find(xml, prefix)
        xml = _swap(xml, p, p.replace(_run_with(p, prefix), _runs(label) + _runs(value, underline=True)))

    group_p = _find(xml, "Группа")
    xml = _swap(xml, group_p, group_p.replace(_run_with(group_p, "_________"), _runs(group_code, underline=True)))
    curator_p = _find(xml, "Куратор группы")
    curator_run = _run_with(curator_p, "уратор группы")
    if curator_name:
        xml = _swap(xml, curator_p, curator_p.replace(curator_run, _runs("уратор группы ") + _runs(curator_name, underline=True)))

    # Присутствовавшие: «1…(ФИО, должность/статус)», «2…», «3…» → по строке на каждого (если указаны).
    people = [line.strip() for line in (note.participants or "").splitlines() if line.strip()]
    if people:
        first, second, third = _find(xml, "1…"), _find(xml, "2…"), _find(xml, "3…")
        template = second
        lines = "".join(
            template.replace(_run_with(template, "2…"), _runs(f"{i}. {person}"))
            for i, person in enumerate(people, start=1)
        )
        xml = _swap(xml, first, lines)
        xml = _swap(xml, second, "")
        xml = _swap(xml, third, "")

    # Цель: после «Цель беседы:» — текст, строки-продолжения из подчёркиваний убираются.
    goal_p = _find(xml, "Цель беседы")
    if note.goal:
        goal_continuation = _next(xml, goal_p)
        xml = _swap(xml, goal_p, goal_p.replace(_run_with(goal_p, "_"), _runs(" " + note.goal)))
        if _only_underscores(goal_continuation):
            xml = _swap(xml, goal_continuation, "")

    # Содержание и итог: «Содержание беседы: ___» + строки; «Результат беседы: ___» + строка.
    content_p = _find(xml, "Содержание беседы")
    content_run = _run_with(content_p, ":")
    result_p = _find_containing(xml, "Результат беседы")
    result_continuation = _next(xml, result_p)
    if note.text:
        xml = _swap(xml, content_p, content_p.replace(content_run, _runs(": " + note.text)))
        # Первые два прогона абзаца с результатом — продолжение подчёркнутых строк содержания.
        lead = re.findall(r"<w:r[ >].*?</w:r>", result_p, re.S)[:2]
        if all(not _plain(r).strip("_ ") and _plain(r) for r in lead):
            trimmed = result_p
            for run in lead:
                trimmed = trimmed.replace(run, "", 1)
            xml = _swap(xml, result_p, trimmed)
            result_p = trimmed
    if note.result:
        tail = _run_with(result_p, ":")
        xml = _swap(xml, result_p, result_p.replace(tail, _runs(": " + note.result)))
        if _only_underscores(result_continuation):
            xml = _swap(xml, result_continuation, "")

    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in order:
            dst.writestr(name, parts[name])
    return out.getvalue()
