"""«Папка куратора» — комплект документов по п. 5.1 положения о кураторе КАИТ № 20 (16 документов).

Платформа ничего не хранит про «папку» сама: по каждому пункту она знает, есть ли в платформе данные для документа,
и даёт ссылки на уже существующие выгрузки (план, список группы, паспорт, карточки, протоколы, табель, отчёт).
Пункты, которые платформа не ведёт (циклограмма, предметы и преподаватели, стипендии, журнал инструктажа,
трудоустройство), показываются как «ведётся вне платформы» — это честнее, чем ручные отметки «готово».

Состояние пункта:
  * `filled`  — данные есть, документ собирается из них;
  * `blank`   — данных пока нет, выгрузка даст пустой бланк (куратор допишет от руки);
  * `outside` — документ ведётся вне платформы;
  * `off`     — раздел платформы выключен (`ENABLED_MODULES`), выгрузки нет."""
import datetime
from dataclasses import dataclass, field
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.modules import module_enabled
from app.models import CuratorReport, GroupEvent, GroupSubject, ParentMeeting, SafetyInstruction, StudentNote, StudyGroup
from app.services import attendance_service, conversation_protocol_service, individual_work_service
from app.services import group_assembly_service, parent_meeting_service

MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)
ROSTER_FIELDS = "full_name,birth_date,phone,guardians,guardian_phones"
CARD_FIELDS = "full_name,group,gender,birth_date,birth_place,registration_address,enrollment_order,previous_education"
MAX_PROTOCOL_LINKS = 200  # беседы в списке выгрузок — не больше (остальные — во вкладке «Индивидуальная работа»)


@dataclass
class Download:
    label: str
    path: str  # путь API (с параметрами) для скачивания
    filename: str


@dataclass
class FolderItem:
    code: str
    title: str
    state: str  # filled / blank / outside / off
    note: str
    downloads: list[Download] = field(default_factory=list)
    open_tab: str | None = None  # вкладка группы, где документ создаётся и правится
    open_part: str | None = None  # раздел внутри вкладки (план → «Родительские собрания»)
    can_add: str | None = None  # что можно завести прямо в папке (`assembly` — протокол общего собрания)


def _year_bounds(year: str) -> tuple[datetime.date, datetime.date]:
    start = int(year[:4])
    return datetime.date(start, 9, 1), datetime.date(start + 1, 8, 31)


def months_of_year(year: str, today: datetime.date) -> list[tuple[int, int]]:
    """Месяцы учебного года (год, месяц) от сентября до текущего включительно; в прошлых годах — все десять."""
    first, last = _year_bounds(year)
    end = min(last, today)
    result = []
    y, m = first.year, first.month
    while (y, m) <= (end.year, end.month):
        result.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return result


def _month_range(y: int, m: int) -> tuple[datetime.date, datetime.date]:
    nxt = datetime.date(y + (m == 12), m % 12 + 1, 1)
    return datetime.date(y, m, 1), nxt - datetime.timedelta(days=1)


def _outside(code: str, title: str, note: str) -> FolderItem:
    return FolderItem(code, title, "outside", note)


def _off(code: str, title: str) -> FolderItem:
    return FolderItem(code, title, "off", "Раздел платформы отключён — выгрузка недоступна")


def build(db: Session, group: StudyGroup, year: str, today: datetime.date) -> list[FolderItem]:
    gid, code = group.id, group.code
    students = attendance_service.get_active_students(db, gid, today)
    events = db.query(GroupEvent).filter(GroupEvent.study_group_id == gid, GroupEvent.school_year == year).count()
    meetings = parent_meeting_service.meetings_of(db, gid, year)
    assemblies = group_assembly_service.assemblies_of(db, gid, year)
    first, last = _year_bounds(year)
    notes = []
    if students:
        notes = [
            n for n in db.query(StudentNote).filter(
                StudentNote.student_id.in_([s.id for s in students]),
                StudentNote.kind.in_(conversation_protocol_service.PROTOCOL_KINDS),
            ).all()
            if first <= individual_work_service.note_date(n) <= last
        ]
        notes.sort(key=individual_work_service.note_date, reverse=True)
    names = {s.id: s for s in students}
    reports = db.query(CuratorReport).filter(CuratorReport.study_group_id == gid, CuratorReport.school_year == year).all()
    reports_by_sem = {r.semester: r for r in reports if r.values_json not in ("", "{}")}
    items: list[FolderItem] = []
    has = module_enabled

    # 5.1.1
    if has("plan"):
        items.append(FolderItem(
            "5.1.1", "План воспитательной работы", "filled" if events else "blank",
            f"Мероприятий в плане: {events}" if events else "Мероприятий пока нет — выгрузится пустой бланк",
            [Download("План группы", f"/events/groups/{gid}/plan.docx?kind=group&year={year}", f"План_группы_{code}_{year}.docx"),
             Download("План куратора", f"/events/groups/{gid}/plan.docx?kind=curator&year={year}", f"План_куратора_{code}_{year}.docx")],
            open_tab="plan"))
    else:
        items.append(_off("5.1.1", "План воспитательной работы"))
    # 5.1.2
    items.append(_outside("5.1.2", "Циклограмма куратора", "Платформа циклограмму не ведёт — храните бумажный экземпляр"))
    # 5.1.3
    if has("dossier"):
        items.append(FolderItem(
            "5.1.3", "Таблица оперативной связи", "filled" if students else "blank",
            f"Студентов в группе: {len(students)}" if students else "В группе нет студентов",
            [Download("Таблица в Word", f"/curator/groups/{gid}/roster-sheet?fields={ROSTER_FIELDS}&title={quote('Таблица оперативной связи ' + code)}",
                      f"Таблица_оперативной_связи_{code}.docx")] if students else [],
            open_tab="students"))
    else:
        items.append(_off("5.1.3", "Таблица оперативной связи"))
    # 5.1.4
    if has("passport"):
        items.append(FolderItem(
            "5.1.4", "Социальный паспорт группы", "filled" if students else "blank",
            "Собирается из досье студентов", [Download("Паспорт в Word", f"/passport/group/{gid}/docx", f"Социальный_паспорт_{code}.docx")],
            open_tab="passport"))
    else:
        items.append(_off("5.1.4", "Социальный паспорт группы"))
    # 5.1.5
    subjects = db.query(GroupSubject).filter(GroupSubject.study_group_id == gid).count()
    items.append(FolderItem(
        "5.1.5", "Предметы и преподаватели с телефонами", "filled" if subjects else "blank",
        f"Дисциплин в справочнике: {subjects}" if subjects else "Справочник пуст — заполните его во вкладке «Успеваемость»",
        open_tab="performance"))
    # 5.1.6
    if has("dossier"):
        items.append(FolderItem(
            "5.1.6", "Личные карточки студентов", "filled" if students else "blank",
            f"Карточек: {len(students)}" if students else "В группе нет студентов",
            [Download("Все карточки в Word", f"/curator/groups/{gid}/cards?fields={CARD_FIELDS}", f"Личные_карточки_{code}.docx")] if students else [],
            open_tab="students"))
    else:
        items.append(_off("5.1.6", "Личные карточки студентов"))
    # 5.1.7
    if has("meetings"):
        items.append(FolderItem(
            "5.1.7", "Протоколы родительских собраний", "filled" if meetings else "blank",
            f"Собраний за год: {len(meetings)}" if meetings else "Собраний пока нет",
            [Download(f"№ {m.number}" + (f" от {m.meeting_date:%d.%m.%Y}" if m.meeting_date else ""),
                      f"/meetings/{m.id}/protocol.docx", f"Протокол_собрания_{m.number}_{code}.docx") for m in meetings],
            open_tab="plan", open_part="meetings"))
    else:
        items.append(_off("5.1.7", "Протоколы родительских собраний"))
    # 5.1.8–5.1.9
    if has("dossier"):
        links = [
            Download(f"{names[n.student_id].full_name} · {individual_work_service.note_date(n):%d.%m.%Y}",
                     f"/students/{n.student_id}/dossier/notes/{n.id}/protocol",
                     f"Протокол_беседы_{names[n.student_id].last_name}_{individual_work_service.note_date(n):%d.%m.%Y}.docx")
            for n in notes[:MAX_PROTOCOL_LINKS]
        ]
        items.append(FolderItem(
            "5.1.8–5.1.9", "Протоколы бесед с родителями и студентами", "filled" if notes else "blank",
            f"Бесед за год: {len(notes)}" if notes else "Бесед пока нет", links,
            open_tab="work" if has("individual_work") else None))
    else:
        items.append(_off("5.1.8–5.1.9", "Протоколы бесед с родителями и студентами"))
    # 5.1.10
    if has("meetings"):
        items.append(FolderItem(
            "5.1.10", "Протоколы общих собраний группы", "filled" if assemblies else "blank",
            f"Собраний за год: {len(assemblies)}" if assemblies else "Собраний пока нет — добавьте протокол кнопкой ниже",
            [Download(f"№ {a.number}" + (f" от {a.assembly_date:%d.%m.%Y}" if a.assembly_date else ""),
                      f"/assemblies/{a.id}/protocol.docx", f"Протокол_общего_собрания_{a.number}_{code}.docx") for a in assemblies],
            can_add="assembly"))
    else:
        items.append(_off("5.1.10", "Протоколы общих собраний группы"))
    # 5.1.11
    if has("dossier"):
        items.append(FolderItem(
            "5.1.11", "Копия плана ИВПР (студенты на внутреннем учёте)", "filled",
            "Записи индивидуальной работы по студентам на внутреннем учёте",
            [Download("Копия в Word", f"/folder/groups/{gid}/ivpr.docx", f"План_ИВПР_{code}.docx")],
            open_tab="work" if has("individual_work") else None))
    else:
        items.append(_off("5.1.11", "Копия плана ИВПР (студенты на внутреннем учёте)"))
    # 5.1.12
    months = months_of_year(year, today)
    pdfs = []
    for y, m in reversed(months):
        d1, d2 = _month_range(y, m)
        pdfs.append(Download(f"{MONTHS[m - 1].capitalize()} {y}", f"/export/pdf/{gid}?date_from={d1}&date_to={d2}", f"Табель_{code}_{y}-{m:02d}.pdf"))
    items.append(FolderItem(
        "5.1.12", "Отчёты о посещаемости по месяцам", "filled" if students else "blank",
        "Табель посещаемости группы за месяц с местом для подписей" if students else "В группе нет студентов",
        pdfs if students else []))
    # 5.1.13
    if has("reports"):
        semester_label = {1: "1 семестр", 2: "2 семестр"}
        items.append(FolderItem(
            "5.1.13", "Отчёт куратора за семестр", "filled" if reports_by_sem else "blank",
            "Показатели внесены или посчитаны платформой" if reports_by_sem else "Показатели посчитаны платформой, ручные поля пусты",
            [Download(semester_label[s], f"/reports/groups/{gid}/report.docx?year={year}&semester={s}", f"Отчёт_куратора_{code}_{s}_семестр.docx") for s in (1, 2)],
            open_tab="report"))
    else:
        items.append(_off("5.1.13", "Отчёт куратора за семестр"))
    # 5.1.14–5.1.16
    if has("passport"):
        items.append(FolderItem(
            "5.1.14", "Списки на стипендию", "filled" if students else "blank",
            "Собирается из досье: студенты с указанной стипендией" if students else "В группе нет студентов",
            [Download("Список в Word", f"/passport/group/{gid}/scholarships?format=docx", f"Стипендии_{code}.docx"),
             Download("Список в Excel", f"/passport/group/{gid}/scholarships?format=xlsx", f"Стипендии_{code}.xlsx")] if students else [],
            open_tab="passport"))
    else:
        items.append(_off("5.1.14", "Списки на стипендию"))
    if has("plan"):
        instructions = db.query(SafetyInstruction).filter(
            SafetyInstruction.study_group_id == gid, SafetyInstruction.school_year == year,
        ).order_by(SafetyInstruction.instruction_date.desc(), SafetyInstruction.id.desc()).all()
        items.append(FolderItem(
            "5.1.15", "Журнал инструктажа по охране труда", "filled" if instructions else "blank",
            f"Инструктажей за год: {len(instructions)}" if instructions else "Инструктажей пока нет",
            [Download(f"{i.instruction_date:%d.%m.%Y} · {i.topic[:60]}", f"/instructions/{i.id}/blank.docx",
                      f"Инструктаж_{code}_{i.instruction_date:%Y-%m-%d}.docx") for i in instructions],
            open_tab="plan", open_part="instructions"))
    else:
        items.append(_off("5.1.15", "Журнал инструктажа по охране труда"))
    items.append(_outside("5.1.16", "Материалы по трудоустройству", "Платформа не ведёт — храните бумажный экземпляр"))
    return items
