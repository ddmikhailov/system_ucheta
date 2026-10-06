"""«Отчёт куратора» за семестр (этап 8): черновик из данных платформы + ручные показатели, выгрузка в Word по образцу
колледжа (`app/templates/curator_report.docx`).

Показатели бланка делятся на три вида:
  * **считаются платформой** (число студентов, дети в кружках, средний % неуважительных пропусков, число родительских
    собраний, мероприятия плана, «есть ли план») — показываются как предложение, куратор может поправить;
  * **вводятся вручную** (ИУП, задолженности, стипендии, сборы, движение контингента, ВКУ и группа риска по решению
    Совета профилактики, «Мой.ID», самоуправление) — хранятся в платформе по семестрам, чтобы цифры не терялись;
  * итоговое значение — внесённое вручную, а если его нет, посчитанное платформой.
Шапка, шрифты и таблицы берутся из образца как есть, подставляются только значения; пустое остаётся для записи от руки."""
import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import CuratorReport, GroupEvent, ParentMeeting, Student, StudentNote, StudentProfile, StudyGroup
from app.services import docx_xml as dx
from app.services import group_event_service, passport_service, stats_service
from app.services.docx_xml import TemplateMismatch

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "curator_report.docx"
MAX_VALUE_LENGTH = 2000


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    hint: str | None = None
    long: bool = False  # многострочное поле (ФИО, комментарий)


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    fields: tuple[Field, ...]


def _events_row(key: str, label: str, two_columns: bool = False) -> list[Field]:
    if two_columns:
        return [Field(f"{key}_c", f"{label}: количество мероприятий"), Field(f"{key}_v", f"{label}: охват (студентов)"),
                Field(f"{key}_comment", f"{label}: комментарий / подтверждающий документ", long=True)]
    return [
        Field(f"{key}_cp", f"{label}: мероприятий — участие"), Field(f"{key}_co", f"{label}: мероприятий — организация"),
        Field(f"{key}_vp", f"{label}: охват — участие"), Field(f"{key}_vo", f"{label}: охват — организация"),
        Field(f"{key}_comment", f"{label}: комментарий / подтверждающий документ", long=True),
    ]


SECTIONS: tuple[Section, ...] = (
    Section("general", "Общие данные", (
        Field("g_students", "Количество студентов"),
        Field("g_extra_edu", "Занятых в кружках доп. образования (несовершеннолетних)", "по «Дополнительному образованию» в досье"),
        Field("g_iup", "Переведённых на ИУП"),
        Field("g_debts", "Имеющих 1 и более академических задолженностей"),
        Field("g_academic", "Получающих академическую стипендию"),
        Field("g_excellent", "Имеющих по результатам промежуточной аттестации «отлично»"),
        Field("g_satisfactory", "Имеющих по результатам промежуточной аттестации 1 оценку «удовлетворительно»"),
        Field("g_social", "Получающих социальную стипендию"),
        Field("g_camps", "Прошедших 5-дневные учебные сборы (от числа без медицинских противопоказаний)"),
        Field("g_unexcused", "Отсутствие по неуважительным причинам, средний % за период", "доля пропусков без уважительной причины по сданным дням"),
    )),
    Section("movement", "Движение контингента группы", (
        Field("m_left_request", "Отчисление по личному заявлению"),
        Field("m_left_college", "Отчисление по инициативе образовательной организации"),
        Field("m_left_failure", "— в том числе в связи с неуспеваемостью"),
        Field("m_transfer", "Перевод в иную образовательную организацию"),
        Field("m_transfer_moscow", "— в том числе г. Москва"),
        Field("m_academic_leave", "Академический отпуск"),
        Field("m_arrived", "Количество прибывших обучающихся"),
    )),
    Section("individual", "Индивидуальная работа с обучающимися", (
        Field("i_vku", "Несовершеннолетних на ВКУ по итогам Совета профилактики"),
        Field("i_vku_added", "— поставлено на учёт за период"),
        Field("i_vku_removed", "— снято с учёта за период"),
        Field("i_vku_first", "— из них зарегистрированных в «Движении Первых»"),
        Field("i_risk", "Несовершеннолетних в группе риска по итогам Совета профилактики"),
        Field("i_risk_added", "— прирост за период"),
        Field("i_risk_removed", "— убытие за период"),
        Field("i_meetings", "Встречи в очном формате с законными представителями (наличие протокола обязательно)",
              "очные родительские собрания и записи «Вызов родителей» за период"),
        Field("i_parent_meetings", "— в том числе родительских собраний (очно, онлайн)", "по разделу «План группы»"),
        Field("i_myid", "Зарегистрированных в системе «Мой.ID» (биометрия)"),
    )),
    Section("documents", "Документация", (
        Field("d_passport", "Социальный паспорт группы (электронный и бумажный)", "в платформе ведётся в электронном виде"),
        Field("d_plan", "План воспитательной работы группы", "«Есть», если в «Плане группы» есть мероприятия"),
        Field("d_cards", "Полностью заполненные личные карточки обучающихся"),
    )),
    Section("events", "Основные мероприятия по направлениям воспитательной работы", tuple(
        _events_row("ev_civic", "1.1 Гражданско-патриотическое")
        + _events_row("ev_cultural", "2.1 Духовно-нравственное и культурно-творческое")
        + _events_row("ev_career", "3.1 Профориентационные мероприятия")
        + _events_row("ev_contests", "3.2 Конкурсы профессионального мастерства")
        + _events_row("ev_instructions", "4.1 Инструктажи (профилактика)", two_columns=True)
        + _events_row("ev_parents", "5.1 Консультации для родителей", two_columns=True)
    )),
    Section("selfgov", "Организация самоуправления в группе", (
        Field("s_1", "Актив группы", long=True), Field("s_2", "Волонтёры", long=True),
        Field("s_3", "Представители студенческого совета отделения", long=True), Field("s_4", "Амбассадоры", long=True),
        Field("s_5", "Участники «Движения Первых»", long=True),
        Field("s_6", "Участники Чемпионатов Профессионального мастерства", long=True),
        Field("s_7", "Участники спортивного и туристского клубов", long=True),
        Field("s_8", "Участники военно-патриотического поискового отряда «Дозор»", long=True),
        Field("s_9", "Участники студенческого медиацентра «Медиакод»", long=True),
    )),
)
FIELD_KEYS = {f.key for s in SECTIONS for f in s.fields}


class UnknownField(ValueError):
    pass


def period(year: str, semester: int) -> tuple[datetime.date, datetime.date]:
    """1-й семестр — сентябрь–январь, 2-й — февраль–август (как в личной карточке)."""
    first = int(year.split("-")[0])
    if semester == 1:
        return datetime.date(first, 9, 1), datetime.date(first + 1, 1, 31)
    return datetime.date(first + 1, 2, 1), datetime.date(first + 1, 8, 31)


def current_semester(day: datetime.date) -> int:
    return 1 if day.month >= 9 or day.month == 1 else 2


def stored_values(db: Session, group_id: int, year: str, semester: int) -> tuple[dict[str, str], CuratorReport | None]:
    row = db.query(CuratorReport).filter_by(study_group_id=group_id, school_year=year, semester=semester).first()
    if row is None:
        return {}, None
    try:
        data = json.loads(row.values_json)
    except ValueError:
        data = {}
    return {k: str(v) for k, v in data.items() if k in FIELD_KEYS and str(v).strip()}, row


def save_values(db: Session, group_id: int, year: str, semester: int, values: dict[str, str | None], user_id: int) -> dict[str, str]:
    """Заменяет ручные значения целиком; пустые не хранятся."""
    unknown = [k for k in values if k not in FIELD_KEYS]
    if unknown:
        raise UnknownField("Неизвестные показатели: " + ", ".join(sorted(unknown)))
    clean = {k: v.strip() for k, v in values.items() if v and v.strip()}
    row = db.query(CuratorReport).filter_by(study_group_id=group_id, school_year=year, semester=semester).first()
    if row is None:
        row = CuratorReport(study_group_id=group_id, school_year=year, semester=semester)
        db.add(row)
    row.values_json = json.dumps(clean, ensure_ascii=False)
    row.updated_by_user_id = user_id
    return clean


# ───────────────────────────── что считает платформа ─────────────────────────────

_EVENT_SECTIONS = {
    "ev_civic": ("civic",),
    "ev_cultural": ("cultural", "spiritual"),
    "ev_career": ("career", "professional"),
}
_CONSULTATION_KINDS = ("conversation", "call", "parent_invited")


def _age(birth: datetime.date, on: datetime.date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def auto_values(db: Session, group: StudyGroup, year: str, semester: int, today: datetime.date) -> dict[str, str]:
    start, end = period(year, semester)
    if start > today:
        return {}  # семестр ещё не начался — нечего считать
    until = min(end, today)
    result: dict[str, str] = {}

    students = passport_service.rosters(db, [group], until)[group.id]
    result["g_students"] = str(len(students))
    ids = [s.id for s in students]
    if ids:
        profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(ids))}
        in_clubs = sum(
            1 for sid in ids
            if (p := profiles.get(sid)) and p.additional_education and p.birth_date and _age(p.birth_date, until) < 18
        )
        result["g_extra_edu"] = str(in_clubs)

    stats = stats_service.compute_period_stats(db, start, until, study_group_id=group.id, only_submitted=True)
    if stats.in_list:
        result["g_unexcused"] = f"{stats.absent_unexcused / stats.in_list * 100:.1f}".replace(".", ",") + " %"

    meetings = [
        m for m in db.query(ParentMeeting).filter(ParentMeeting.study_group_id == group.id, ParentMeeting.school_year == year)
        if m.meeting_date and start <= m.meeting_date <= end
    ]
    notes = []
    if ids:
        notes = db.query(StudentNote).filter(
            StudentNote.student_id.in_(ids), StudentNote.kind.in_(_CONSULTATION_KINDS)).all()
        notes = [n for n in notes if start <= (n.occurred_on or n.created_at.date()) <= end]
    result["i_parent_meetings"] = str(len(meetings))
    result["i_meetings"] = str(sum(1 for m in meetings if m.meeting_format == "in_person") + sum(1 for n in notes if n.kind == "parent_invited"))
    result["ev_parents_c"] = str(len(notes))

    events = [e for e in group_event_service.events_of(db, group.id, year) if e.status == "done" and e.event_date and start <= e.event_date <= end]
    for key, sections in _EVENT_SECTIONS.items():
        mine = [e for e in events if e.section in sections]
        if mine:
            result[f"{key}_cp"] = str(len(mine))
            result[f"{key}_comment"] = "; ".join(f"{e.title} ({e.event_date.strftime('%d.%m.%Y')})" for e in mine)[:MAX_VALUE_LENGTH]
    result["d_passport"] = "Есть (электронный)"
    if group_event_service.events_of(db, group.id, year):
        result["d_plan"] = "Есть"
    return result


def effective_values(stored: dict[str, str], auto: dict[str, str]) -> dict[str, str]:
    return {key: stored.get(key) or auto.get(key) or "" for key in FIELD_KEYS}


# ───────────────────────────── выгрузка в Word ─────────────────────────────

# Строки таблиц образца: номер строки (без шапки) → ключи значений в порядке строк внутри ячейки.
_ROWS: dict[str, list[list[str]]] = {
    "Показатели": [[k] for k in ("g_students", "g_extra_edu", "g_iup", "g_debts", "g_academic", "g_excellent",
                                  "g_satisfactory", "g_social", "g_camps", "g_unexcused")],
    "Причины": [["m_left_request"], ["m_left_college", "m_left_failure"], ["m_transfer", "m_transfer_moscow"],
                ["m_academic_leave"], ["m_arrived"]],
    "Критерии_individual": [["i_vku", "i_vku_added", "i_vku_removed", "i_vku_first"], ["i_risk", "i_risk_added", "i_risk_removed"],
                            ["i_meetings", "i_parent_meetings"], ["i_myid"]],
    "Критерии_documents": [["d_passport"], ["d_plan"], ["d_cards"]],
    "№": [[f"s_{i}"] for i in range(1, 10)],
}
# Строки таблицы мероприятий образца (индекс строки в таблице) → ключ показателя и число ячеек данных.
_EVENT_ROWS = {3: ("ev_civic", 4), 6: ("ev_cultural", 4), 9: ("ev_career", 4), 10: ("ev_contests", 4),
               12: ("ev_instructions", 2), 14: ("ev_parents", 2)}


def _lines(values: dict[str, str], keys: list[str]) -> str:
    texts = [values.get(k, "") for k in keys]
    if not any(texts):
        return ""
    return "\n".join(t or "—" for t in texts) if len(texts) > 1 else texts[0]


def _tables(xml: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"<w:tbl>.*?</w:tbl>", xml, re.S)]


def _fill_rows(table: str, row_keys: list[list[str]], values: dict[str, str], value_cell: int) -> str:
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    if len(rows) != len(row_keys) + 1:
        raise TemplateMismatch(f"в таблице образца отчёта ожидалось {len(row_keys) + 1} строк, найдено {len(rows)}")
    for row, keys in zip(rows[1:], row_keys, strict=True):
        cells = dx.cells_of(row)
        text = _lines(values, keys)
        if text:
            table = table.replace(row, row.replace(cells[value_cell], dx.fill_cell(cells[value_cell], text, 24), 1), 1)
    return table


def _fill_events(table: str, values: dict[str, str]) -> str:
    rows = re.findall(r"<w:tr[ >].*?</w:tr>", table, re.S)
    if len(rows) != 15:
        raise TemplateMismatch("в таблице мероприятий образца ожидалось 15 строк")
    for index, (key, count) in _EVENT_ROWS.items():
        row = rows[index]
        cells = dx.cells_of(row)
        if len(cells) != count + 3:
            raise TemplateMismatch(f"строка {index} таблицы мероприятий: ожидалось {count + 3} ячеек, найдено {len(cells)}")
        names = ["cp", "co", "vp", "vo"] if count == 4 else ["c", "v"]
        new = row
        for offset, name in enumerate(names):
            text = values.get(f"{key}_{name}", "")
            if text:
                new = new.replace(cells[2 + offset], dx.fill_cell(cells[2 + offset], text, 24), 1)
        comment = values.get(f"{key}_comment", "")
        if comment:
            last = cells[-1]
            new = new.replace(last, dx.fill_cell(last, comment, 20) if not dx.plain(last).strip() else last, 1)
        table = table.replace(row, new, 1)
    return table


def build_docx(*, group_code: str, year: str, semester: int, values: dict[str, str]) -> bytes:
    parts, order = dx.read_template(TEMPLATE_PATH)
    xml = parts["word/document.xml"].decode("utf-8")
    first, second = year.split("-")
    xml = dx.rebuild(xml, dx.find(xml, "ЗА ______СЕМЕСТР"), dx.runs(f"ЗА {'I' if semester == 1 else 'II'} СЕМЕСТР {first}/{second} УЧЕБНОГО ГОДА", 28, bold=True))
    xml = dx.rebuild(xml, dx.find(xml, "______________УЧЕБНОЙ ГРУППЫ"), dx.runs(f"{group_code} УЧЕБНОЙ ГРУППЫ", 28, bold=True))

    tables = _tables(xml)
    if len(tables) != 6:
        raise TemplateMismatch(f"в образце отчёта ожидалось 6 таблиц, найдено {len(tables)}")
    heads = [dx.plain(re.findall(r"<w:tr[ >].*?</w:tr>", t, re.S)[0]).strip() for _, _, t in tables]
    plan = [
        ("Показатели", _ROWS["Показатели"], 1), ("Причины", _ROWS["Причины"], 1),
        ("Критерии", _ROWS["Критерии_individual"], 1), ("Критерии", _ROWS["Критерии_documents"], 1),
        (None, None, None), ("№", _ROWS["№"], 2),
    ]
    out, cursor = [], 0
    for (start, end, table), (head, row_keys, cell), found in zip(tables, plan, heads, strict=True):
        if head is not None and not found.startswith(head):
            raise TemplateMismatch(f"таблица образца отчёта {found[:30]!r} не совпадает с ожидаемой {head!r}")
        new = _fill_events(table, values) if head is None else _fill_rows(table, row_keys, values, cell)
        out.append(xml[cursor:start] + new)
        cursor = end
    xml = "".join(out) + xml[cursor:]
    return dx.write_docx(parts, order, dx.strip_ids(xml))
