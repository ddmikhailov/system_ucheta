"""Общие приёмы правки образцов Word на уровне XML (без сторонних библиотек): поиск абзацев по тексту, замена
одного фрагмента с проверкой «найден ровно один раз», сборка прогонов в шрифте образца, упаковка в .docx.
Если образец заменят на другой по структуре, правка падает понятной `TemplateMismatch`, а не выдаёт испорченный документ."""
import datetime
import io
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


class TemplateMismatch(RuntimeError):
    """Образец документа не совпадает с тем, что ожидает сервис."""


def long_date(d: datetime.date) -> str:
    """«06» октября 2026 г. — как в образцах: «___» __________ 20__ г."""
    return f"«{d.day:02d}» {MONTHS_GENITIVE[d.month - 1]} {d.year} г."


def runs(parts: list[tuple[str, bool]] | str, size: int = 28, *, bold: bool = False) -> str:
    """Части (текст, подчеркнуть) → прогоны Times New Roman; переводы строк в тексте — разрывы строки."""
    if isinstance(parts, str):
        parts = [(parts, False)]
    out = []
    for text, underline in parts:
        rpr = (
            '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
            f'{"<w:b/>" if bold else ""}{"<w:u w:val=" + chr(34) + "single" + chr(34) + "/>" if underline else ""}'
            f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
        )
        for i, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
            out.append(f'<w:r>{rpr}{"<w:br/>" if i else ""}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
    return "".join(out)


def plain(xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


def paragraphs(xml: str) -> list[str]:
    return re.findall(r"<w:p[ >].*?</w:p>", xml[xml.index("<w:body>"):], re.S)


def find(xml: str, startswith: str) -> str:
    found = [p for p in paragraphs(xml) if plain(p).startswith(startswith)]
    if len(found) != 1:
        raise TemplateMismatch(f"в образце не найден (или найден не один раз) абзац: {startswith[:50]!r}")
    return found[0]


def swap(xml: str, old: str, new: str) -> str:
    if xml.count(old) != 1:
        raise TemplateMismatch(f"в образце не найден (или найден не один раз) фрагмент: {old[:70]!r}")
    return xml.replace(old, new)


def next_paragraph(xml: str, paragraph: str) -> str:
    items = paragraphs(xml)
    return items[items.index(paragraph) + 1]


def only_underscores(paragraph: str) -> bool:
    return not plain(paragraph).strip("_ ")


def run_with(paragraph: str, text_prefix: str) -> str:
    """Единственный прогон абзаца, текст которого начинается с `text_prefix` (после необязательного пробела)."""
    found = [r for r in re.findall(r"<w:r[ >].*?</w:r>", paragraph, re.S) if plain(r).lstrip().startswith(text_prefix)]
    if len(found) != 1:
        raise TemplateMismatch(f"в абзаце образца не найден прогон: {text_prefix!r}")
    return found[0]


def rebuild_copy(paragraph: str, new_runs: str) -> str:
    """Копия абзаца с теми же свойствами (`pPr`), но с новыми прогонами (без идентификаторов абзаца)."""
    properties = paragraph[paragraph.index("<w:pPr>"): paragraph.index("</w:pPr>") + len("</w:pPr>")] if "<w:pPr>" in paragraph else ""
    return strip_ids(f"{paragraph[: paragraph.index('>') + 1]}{properties}{new_runs}</w:p>")


def rebuild(xml: str, paragraph: str, new_runs: str) -> str:
    """Абзац заменяется копией с теми же свойствами (`pPr`) и новыми прогонами."""
    return swap(xml, paragraph, rebuild_copy(paragraph, new_runs))


def read_template(path: Path) -> tuple[dict[str, bytes], list[str]]:
    with zipfile.ZipFile(path) as src:
        return {i.filename: src.read(i.filename) for i in src.infolist()}, [i.filename for i in src.infolist()]


def write_docx(parts: dict[str, bytes], order: list[str], xml: str) -> bytes:
    parts = dict(parts)
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in order:
            dst.writestr(name, parts[name])
    return out.getvalue()


def fill_cell(cell: str, text: str, size: int = 22) -> str:
    """Пустая ячейка образца → ячейка с текстом."""
    if not text:
        return cell
    return cell.replace("</w:p></w:tc>", f"{runs(text, size)}</w:p></w:tc>", 1)


def cells_of(row: str) -> list[str]:
    return re.findall(r"<w:tc>.*?</w:tc>", row, re.S)


def strip_ids(xml: str) -> str:
    """Копии строк образца без повторных идентификаторов абзацев (w14:paraId/textId)."""
    return re.sub(r' w14:(?:paraId|textId)="[0-9A-Fa-f]+"', "", xml)
