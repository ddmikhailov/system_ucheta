"""«Личная карточка обучающегося» в Word — по образцу колледжа (`app/templates/student_card.docx`).

Куратор выбирает, какие поля бланка заполнить из платформы; невыбранные остаются пустыми строками бланка для записи
от руки (примеры образца — «пример» — всегда убираются). Оценки, практики, ГИА и приказы ведёт учебная часть, у платформы
этих данных нет: эти разделы можно оставить пустыми (по умолчанию) или убрать из документа. Один документ может
содержать карточки всей группы — каждая с новой страницы.

Работа идёт на уровне XML образца (как `absence_sheet_service`): каждая подстановка проверяет, что нужное место найдено
ровно один раз, — иначе `TemplateMismatch`, а не испорченный документ. Особые категории досье в карточку не попадают."""
import datetime
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from app.models import AttendanceMark, DaySubmission, MarkCode, Student, StudentProfile, StudyGroup
from app.services import passport_service

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "student_card.docx"
SEMESTERS = 10  # столько столбцов в таблице пропусков образца


@dataclass(frozen=True)
class Field_:
    key: str
    title: str


# Поля, которые куратор выбирает; порядок — как в бланке.
FIELDS: list[Field_] = [
    Field_("full_name", "ФИО"),
    Field_("group", "Группа"),
    Field_("gender", "Пол"),
    Field_("birth_date", "Дата рождения"),
    Field_("birth_place", "Место рождения"),
    Field_("registration_address", "Адрес регистрации"),
    Field_("enrollment_order", "Приказ о зачислении"),
    Field_("previous_education", "Образование до поступления"),
    Field_("absences", "Число пропущенных занятий (по семестрам)"),
    Field_("social_work", "Общественная работа (доп. образование)"),
]
FIELD_KEYS = {f.key for f in FIELDS}


class UnknownField(ValueError):
    pass


class TemplateMismatch(RuntimeError):
    """Образец документа не совпадает с тем, что ожидает сервис."""


def parse_fields(raw: str) -> list[str]:
    keys = list(dict.fromkeys(k.strip() for k in raw.split(",") if k.strip()))
    unknown = [k for k in keys if k not in FIELD_KEYS]
    if unknown:
        raise UnknownField("Неизвестные поля карточки: " + ", ".join(unknown))
    if not keys:
        raise UnknownField("Выберите хотя бы одно поле")
    return keys


@dataclass
class CardData:
    full_name: str
    group_code: str
    gender: str | None = None
    birth_date: datetime.date | None = None
    profile: dict[str, str | None] = field(default_factory=dict)  # birth_place, registration_address, …
    # Пропуски по семестрам: номер семестра (1..10) → (по уважительной причине, по неуважительной); только семестры,
    # по которым в платформе есть сданные дни.
    absences: dict[int, tuple[int, int]] = field(default_factory=dict)


def semester_of(day: datetime.date, first_year: int) -> int:
    """Номер семестра с начала обучения: сентябрь–январь — нечётный, февраль–август — чётный."""
    if day.month >= 9:
        return 2 * (day.year - first_year) + 1
    if day.month == 1:
        return 2 * (day.year - 1 - first_year) + 1
    return 2 * (day.year - 1 - first_year) + 2


def first_study_year(group: StudyGroup, today: datetime.date) -> int:
    """Год начала первого курса: по текущему курсу группы (дата зачисления в платформе — дата начала учёта, не приказа)."""
    current = today.year if today.month >= 9 else today.year - 1
    return current - (group.course - 1)


def collect(db: Session, group: StudyGroup, today: datetime.date, only_student_id: int | None = None) -> list[CardData]:
    """Данные карточек студентов, числящихся в группе сегодня (по фамилии и имени); с `only_student_id` — одного."""
    students: list[Student] = passport_service.rosters(db, [group], today)[group.id]
    if only_student_id is not None:
        students = [s for s in students if s.id == only_student_id]
    if not students:
        return []
    ids = [s.id for s in students]
    profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(ids))}
    first_year = first_study_year(group, today)
    since = datetime.date(first_year, 9, 1)

    submitted = {
        semester_of(d, first_year) for (d,) in db.query(DaySubmission.date).filter(
            DaySubmission.study_group_id == group.id, DaySubmission.date >= since, DaySubmission.date <= today)
    }
    totals: dict[int, dict[int, list[int]]] = {sid: {} for sid in ids}
    rows = (
        db.query(AttendanceMark.student_id, AttendanceMark.date, MarkCode.is_excused, MarkCode.counts_as_present)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .filter(AttendanceMark.student_id.in_(ids), AttendanceMark.date >= since, AttendanceMark.date <= today)
    )
    for row in rows:
        if row.counts_as_present:  # опоздание — не пропуск
            continue
        semester = semester_of(row.date, first_year)
        pair = totals[row.student_id].setdefault(semester, [0, 0])
        pair[0 if row.is_excused else 1] += 1

    cards = []
    for s in students:
        p = profiles.get(s.id)
        absences = {
            sem: tuple(totals[s.id].get(sem, [0, 0])) for sem in sorted(submitted) if 1 <= sem <= SEMESTERS
        }
        cards.append(CardData(
            full_name=s.full_name, group_code=group.code, gender=p.gender if p else None,
            birth_date=p.birth_date if p else None,
            profile={k: getattr(p, k, None) if p else None
                     for k in ("birth_place", "registration_address", "enrollment_order", "previous_education",
                               "additional_education")},
            absences=absences,
        ))
    return cards


# ───────────────────────────── сборка документа ─────────────────────────────

_RPR = ('<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>{extra}'
        '<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>')


def _runs(parts: list[tuple[str, bool]], size: int) -> str:
    """Части (текст, подчёркнуть) → прогоны образца; переводы строк внутри текста — разрывы строки."""
    out = []
    for text, underline in parts:
        rpr = _RPR.format(extra='<w:u w:val="single"/>' if underline else "", size=size)
        for i, line in enumerate(text.replace("\r\n", "\n").split("\n")):
            out.append(f'<w:r>{rpr}{"<w:br/>" if i else ""}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
    return "".join(out)


def _plain(xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


def _split_body(body: str) -> tuple[list[str], str]:
    """Верхнеуровневые элементы тела (абзацы и таблицы) и хвост `<w:sectPr>…`."""
    tail_at = body.rindex("<w:sectPr")
    content, tail = body[:tail_at], body[tail_at:]
    items, pos = [], 0
    pattern = re.compile(r"<w:tbl>.*?</w:tbl>|<w:p[ >].*?</w:p>", re.S)
    while pos < len(content):
        m = pattern.match(content, pos)
        if m is None:
            raise TemplateMismatch("в образце карточки встретился элемент, который сервис не разбирает")
        items.append(m.group(0))
        pos = m.end()
    return items, tail


def _index(items: list[str], startswith: str, *, paragraph: bool = True) -> int:
    found = [i for i, x in enumerate(items) if x.startswith("<w:p") == paragraph and _plain(x).startswith(startswith)]
    if len(found) != 1:
        raise TemplateMismatch(f"в образце карточки не найден (или найден не один раз) элемент: {startswith[:50]!r}")
    return found[0]


def _set_paragraph(items: list[str], startswith: str, parts: list[tuple[str, bool]], size: int) -> None:
    i = _index(items, startswith)
    p = items[i]
    properties = p[p.index("<w:pPr>"): p.index("</w:pPr>") + len("</w:pPr>")] if "<w:pPr>" in p else ""
    open_tag = p[: p.index(">") + 1]
    items[i] = f"{open_tag}{properties}{_runs(parts, size)}</w:p>"


_BLANK = "_"


def _fill_cell(cell: str, text: str) -> str:
    run = _runs([(text, False)], 20)
    return cell.replace("</w:p></w:tc>", f"{run}</w:p></w:tc>", 1)


def _fill_absences(table: str, card: CardData) -> str:
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    if len(rows) != 4:
        raise TemplateMismatch("таблица пропусков образца: ожидалось 4 строки")
    for row_no, row in ((2, rows[2]), (3, rows[3])):
        cells = re.findall(r"<w:tc>.*?</w:tc>", row, re.S)
        if len(cells) != SEMESTERS + 2:
            raise TemplateMismatch("таблица пропусков образца: ожидалось 12 столбцов")
        new_row, total = row, 0
        for sem in range(1, SEMESTERS + 1):
            if sem in card.absences:
                value = card.absences[sem][0 if row_no == 2 else 1]
                total += value
                new_row = new_row.replace(cells[sem], _fill_cell(cells[sem], str(value)), 1)
        if card.absences:
            new_row = new_row.replace(cells[-1], _fill_cell(cells[-1], str(total)), 1)
        table = table.replace(row, new_row, 1)
    return table


_SECTIONS = ("II. Оценки", "III. Практическая", "IV. Число пропущенных", "V. Государственная", "VI. Итоговый",
             "VII. Общественная", "VIII. Взыскания")


def _render_card(template_items: list[str], card: CardData, chosen: set[str], blank_sections: bool) -> list[str]:
    items = list(template_items)
    P = card.profile

    # Шапка. Примеры образца («пример») убираются всегда: либо значение платформы, либо чистая строка бланка.
    name = card.full_name
    _set_paragraph(items, "Обучающийся", [("Обучающийся ", False)] + ([(name, True)] if "full_name" in chosen else [(_BLANK * 40, False)]), 28)
    _set_paragraph(items, "Зачислен на", [("Зачислен на ____ курс в группу ", False)] + (
        [(card.group_code, True)] if "group" in chosen else [(_BLANK * 20, False)]), 28)
    _set_paragraph(items, "по специальности", [("по специальности " + _BLANK * 40, False)], 28)
    _set_paragraph(items, "Дата зачисления", [("Дата зачисления: ____.____.________", False)], 28)

    _set_paragraph(items, "1. (ФИО)", [("1. (ФИО) ", False)] + ([(name, True)] if "full_name" in chosen else [(_BLANK * 40, False)]), 24)
    if "gender" in chosen and card.gender in ("male", "female"):
        _set_paragraph(items, "2. Пол", [
            ("2. Пол: ", False), ("женский", card.gender == "female"), (", ", False),
            ("мужской", card.gender == "male"), (" (подчеркнуть)", False)], 24)
    if "birth_date" in chosen and card.birth_date:
        _set_paragraph(items, "3. Год, месяц и число рождения", [
            ("3. Год, месяц и число рождения ", False), (card.birth_date.strftime("%d.%m.%Y"), True)], 24)

    def line(startswith: str, label: str, key: str, selected: str, size: int = 24) -> None:
        value = P.get(key) if selected in chosen else None
        _set_paragraph(items, startswith, [(label, False), (value, True)] if value else [(label + _BLANK * 40, False)], size)

    line("4. Место рождения", "4. Место рождения: ", "birth_place", "birth_place")
    line("5. Адрес регистрации", "5. Адрес регистрации: ", "registration_address", "registration_address")
    order = P.get("enrollment_order") if "enrollment_order" in chosen else None
    _set_paragraph(items, "Приказ №", [("Приказ ", False), (order, True)] if order
                   else [("Приказ № ___________ от ___________________________", False)], 24)
    education = P.get("previous_education") if "previous_education" in chosen else None
    _set_paragraph(items, "11 классов", [(education, True)] if education else [(_BLANK * 90, False)], 24)

    # Общественная работа ← «Дополнительное образование» досье (строка 1; строка 2 остаётся для записи от руки).
    social = P.get("additional_education") if "social_work" in chosen else None
    if social:
        _set_paragraph(items, "1_", [("1. ", False), (social, True)], 28)

    # Границы разделов II–VIII: заголовок и всё до следующего заголовка (таблицы и пустые абзацы).
    heading = {name_: _index(items, name_) for name_ in _SECTIONS}
    bounds = sorted(heading.values()) + [len(items)]
    order_of = {name_: (heading[name_], bounds[bounds.index(heading[name_]) + 1]) for name_ in _SECTIONS}

    # Таблица пропусков (раздел IV).
    start, end = order_of["IV. Число пропущенных"]
    if "absences" in chosen and card.absences:
        for i in range(start, end):
            if items[i].startswith("<w:tbl>"):
                items[i] = _fill_absences(items[i], card)

    if not blank_sections:
        keep = {"IV. Число пропущенных": "absences" in chosen, "VII. Общественная": "social_work" in chosen}
        drop: list[int] = []
        for name_ in _SECTIONS:
            if not keep.get(name_, False):
                s, e = order_of[name_]
                drop.extend(range(s, e))
        items = [x for i, x in enumerate(items) if i not in set(drop)]
    return items


def build_docx(cards: list[CardData], fields: list[str], *, blank_sections: bool = True) -> bytes:
    with zipfile.ZipFile(TEMPLATE_PATH) as src:
        parts = {info.filename: src.read(info.filename) for info in src.infolist()}
        order = [info.filename for info in src.infolist()]
    xml = parts["word/document.xml"].decode("utf-8")
    body_start = xml.index("<w:body>") + len("<w:body>")
    body_end = xml.index("</w:body>")
    template_items, tail = _split_body(xml[body_start:body_end])

    chosen = set(fields)
    pages = []
    for card in cards:
        items = _render_card(template_items, card, chosen, blank_sections)
        pages.append("".join(items))
    page_break = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
    body = page_break.join(pages)
    body = re.sub(r' w14:(?:paraId|textId)="[0-9A-Fa-f]+"', "", body)  # копии без повторных идентификаторов абзацев
    xml = xml[:body_start] + body + tail + xml[body_end:]

    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in order:
            dst.writestr(name, parts[name])
    return out.getvalue()
