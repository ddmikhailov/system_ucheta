"""«Лист ознакомления и письменного объяснения по пропускам и опозданиям» (этап 6+).

Документ собирается из образца колледжа — `app/templates/absence_sheet.docx`: шрифты, поля, подвал, таблицы
и все постоянные тексты (Правила внутреннего распорядка) берутся из него как есть, подставляются только
сведения о студенте и таблица дней. Образец содержал две колонки с академическими часами — по решению
пользователя часов в листе нет, остаются только дни с пропусками: «№ · Дата · Отметка».

Работа идёт на уровне XML образца (стандартные `zipfile` и строки, без новых зависимостей). Каждая подстановка
проверяет, что нужное место в образце нашлось ровно один раз, — если образец заменят на другой по структуре,
формирование листа упадёт с понятной ошибкой, а не выдаст испорченный документ."""
import datetime
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from app.models import AttendanceMark, MarkCode, Student

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "absence_sheet.docx"
MAX_RANGE_DAYS = 366

MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

_RFONTS = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman"/>'
# Ширины колонок таблицы дней: «№», «Дата», «Отметка» — вместе столько же, сколько сетка таблицы в образце (7500).
_COLUMN_WIDTHS = (700, 1600, 5200)


class TemplateMismatch(RuntimeError):
    """Образец документа не совпадает с тем, что ожидает сервис."""


@dataclass
class SheetRow:
    date: datetime.date
    label: str  # название отметки из справочника: «Неуважительная причина», «Опоздание» …
    is_late: bool  # опоздание (присутствовал); иначе — пропуск
    is_excused: bool


@dataclass
class SheetTotals:
    days_with_absences: int
    late: int
    truancy: int  # пропуски без уважительной причины (прогулы)


def collect_rows(
    db: Session, student: Student, date_from: datetime.date, date_to: datetime.date, include_excused: bool = False,
) -> list[SheetRow]:
    """Отметки студента за период: пропуски без уважительной причины и опоздания; пропуски по уважительной
    причине (больничный, приказ, практика…) — только если включены явно."""
    rows = (
        db.query(AttendanceMark.date, MarkCode.name, MarkCode.counts_as_present, MarkCode.is_excused)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .filter(AttendanceMark.student_id == student.id, AttendanceMark.date >= date_from,
                AttendanceMark.date <= date_to)
        .order_by(AttendanceMark.date)
    )
    result = []
    for r in rows:
        is_late = bool(r.counts_as_present)
        if not is_late and r.is_excused and not include_excused:
            continue
        result.append(SheetRow(date=r.date, label=r.name, is_late=is_late, is_excused=bool(r.is_excused)))
    return result


def totals(rows: list[SheetRow]) -> SheetTotals:
    absences = [r for r in rows if not r.is_late]
    return SheetTotals(
        days_with_absences=len({r.date for r in absences}),
        late=sum(1 for r in rows if r.is_late),
        truancy=sum(1 for r in absences if not r.is_excused),
    )


def format_date(d: datetime.date) -> str:
    return d.strftime("%d.%m.%Y")


def _long_date(d: datetime.date) -> str:
    """«04» октября 2026 г. — как в образце: «____» __________ 20__ г."""
    return f"«{d.day:02d}» {MONTHS_GENITIVE[d.month - 1]} {d.year} г."


# Формы, зависящие от рода: (как в образце, мужской род, женский род). Правила внутреннего распорядка
# («обучающийся обязан…») — цитата из локального акта, их не склоняем. Пол не указан — образец остаётся как есть.
GENDER_FORMS = (
    ("обучающегося(ейся)", "обучающегося", "обучающейся"),
    ("обучающийся(аяся)", "обучающийся", "обучающаяся"),
    ("ознакомлен(а)", "ознакомлен", "ознакомлена"),
    ("согласен(на)", "согласен", "согласна"),
    ("(Ф.И.О. обучающегося полностью)", "(Ф.И.О. обучающегося полностью)", "(Ф.И.О. обучающейся полностью)"),
    ("Подпись обучающегося", "Подпись обучающегося", "Подпись обучающейся"),
)


def _apply_gender(xml: str, gender: str | None) -> str:
    if gender not in ("male", "female"):
        return xml
    for original, male, female in GENDER_FORMS:
        if original not in xml:
            raise TemplateMismatch(f"в образце листа не найдена форма, зависящая от пола: {original!r}")
        xml = xml.replace(original, male if gender == "male" else female)
    return xml


def _replace_once(xml: str, old: str, new: str) -> str:
    if xml.count(old) != 1:
        raise TemplateMismatch(f"в образце листа не найден (или найден не один раз) фрагмент: {old[:70]!r}")
    return xml.replace(old, new)


def _t(text: str) -> str:
    return escape(text)


def _cell(width: int, text: str, *, bold: bool, margin: int, size: int) -> str:
    run = (
        f'<w:r><w:rPr>{_RFONTS}{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/></w:rPr>'
        f'<w:t xml:space="preserve">{_t(text)}</w:t></w:r>'
    )
    return (
        f'<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="{width}"/><w:vAlign w:val="center"/>'
        f'<w:tcMar><w:top w:w="{margin}" w:type="dxa"/><w:start w:w="45" w:type="dxa"/>'
        f'<w:bottom w:w="{margin}" w:type="dxa"/><w:end w:w="45" w:type="dxa"/></w:tcMar></w:tcPr>'
        f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>{run}</w:p></w:tc>'
    )


def _row(cells: list[str], header: bool = False) -> str:
    props = '<w:cantSplit/><w:trHeight w:val="380" w:hRule="atLeast"/>' + ("<w:tblHeader/>" if header else "")
    return f"<w:tr><w:trPr>{props}</w:trPr>{''.join(cells)}</w:tr>"


def _days_table(original_table: str, rows: list[SheetRow]) -> str:
    """Таблица дней: оформление (границы, поля ячеек, высота строк, шрифты) — как у таблицы образца."""
    head = original_table[: original_table.index("<w:tblGrid>")]
    grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in _COLUMN_WIDTHS) + "</w:tblGrid>"
    w1, w2, w3 = _COLUMN_WIDTHS
    header = _row([
        _cell(w1, "№", bold=True, margin=45, size=18),
        _cell(w2, "Дата", bold=True, margin=45, size=18),
        _cell(w3, "Пропуск / опоздание (отметка в журнале)", bold=True, margin=45, size=18),
    ], header=True)
    body = "".join(
        _row([
            _cell(w1, str(i), bold=False, margin=38, size=20),
            _cell(w2, format_date(r.date), bold=False, margin=38, size=20),
            _cell(w3, r.label, bold=False, margin=38, size=20),
        ])
        for i, r in enumerate(rows, start=1)
    )
    return f"{head}{grid}{header}{body}</w:tbl>"


def build_docx(
    *, student_name: str, group_code: str, department_name: str, curator_name: str | None,
    date_from: datetime.date, date_to: datetime.date, rows: list[SheetRow], gender: str | None = None,
) -> bytes:
    with zipfile.ZipFile(TEMPLATE_PATH) as src:
        parts = {info.filename: src.read(info.filename) for info in src.infolist()}
        order = [info.filename for info in src.infolist()]
    xml = parts["word/document.xml"].decode("utf-8")

    # Левый верхний угол: отделение и группа. Строку для ФИО заведующего оставляем пустой (пишут от руки:
    # в дательном падеже ФИО автоматически не склонить).
    xml = _replace_once(xml, "учебным отделением «__________»", f"учебным отделением «{_t(department_name)}»")
    xml = _replace_once(xml, "от обучающегося(ейся) группы ______________", f"от обучающегося(ейся) группы {_t(group_code)}")
    # Строка ФИО над подписью «(Ф.И.О. обучающегося полностью)»: значение — подчёркнуто, как заполненная строка.
    xml = _replace_once(
        xml,
        '<w:sz w:val="22"/></w:rPr><w:t>________________________________________</w:t></w:r></w:p><w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="center"/>',
        f'<w:sz w:val="22"/><w:u w:val="single"/></w:rPr><w:t>{_t(student_name)}</w:t></w:r></w:p><w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="center"/>',
    )
    xml = _replace_once(xml, "Я, ________________________________________________, обучающийся(аяся) группы ____________, подтверждаю",
                        f"Я, {_t(student_name)}, обучающийся(аяся) группы {_t(group_code)}, подтверждаю")
    xml = _replace_once(
        xml, "Период: с «____» __________ 20__ г. по «____» __________ 20__ г.",
        f"Период: с {_long_date(date_from)} по {_long_date(date_to)}",
    )

    starts = [m.start() for m in re.finditer("<w:tbl>", xml)]
    if len(starts) != 3:
        raise TemplateMismatch(f"в образце листа ожидалось 3 таблицы, найдено {len(starts)}")
    table_end = xml.index("</w:tbl>", starts[1]) + len("</w:tbl>")
    original_table = xml[starts[1]:table_end]
    if "Количество академических часов" not in original_table:
        raise TemplateMismatch("вторая таблица образца — не таблица дней с часами")
    xml = xml[: starts[1]] + _days_table(original_table, rows) + xml[table_end:]

    t = totals(rows)
    xml = _replace_once(
        xml,
        "Итого за указанный период: дней с пропусками ________; академических часов по расписанию в указанные дни ________; "
        "фактически пропущено ________ ак. часов; опозданий ________; прогулов ________.",
        f"Итого за указанный период: дней с пропусками {t.days_with_absences}; опозданий {t.late}; прогулов {t.truancy}.",
    )
    if curator_name:
        # Подпись остаётся чертой для росписи, расшифровка подписи — ФИО куратора (подчёркнуто, как заполненная строка).
        curator_tail = (
            "</w:t></w:r><w:r><w:rPr>" + _RFONTS + '<w:sz w:val="19"/><w:u w:val="single"/></w:rPr>'
            f'<w:t xml:space="preserve"> {_t(curator_name)}'
        )
    else:
        curator_tail = " ______________________________"
    xml = _replace_once(
        xml, "Куратор учебной группы: ____________________ / ______________________________",
        f"Куратор учебной группы: ____________________ /{curator_tail}",
    )

    xml = _apply_gender(xml, gender)

    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in order:
            dst.writestr(name, parts[name])
    return out.getvalue()
