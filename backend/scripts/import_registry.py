"""Загрузка реестра контингента колледжа (выгрузка xlsx) — группы и студенты
всех отделений.

Что делает:
  * отделение определяется по адресу площадки (ADDRESS_TO_DEPARTMENT), нужных
    отделений, которых ещё нет, заводит;
  * группы: код на платформе — без хвоста реестра (год набора «-26» или
    номер подгруппы «.8»): «ИИ112-26» → «ИИ112»; группы, отличавшиеся только
    хвостом, считаются одной — студенты подгрупп переходят в основную, а
    опустевшие подгруппы скрываются. Существующая группа переименовывается
    вместе с кураторами, историей и отметками;
  * студенты: совпадение по группе + ФИО; не найденного в своей группе ищем по
    ФИО среди ещё не сопоставленных (однозначно) и переводим; иначе создаём;
    статус («Обучается» / «В академическом отпуске») берётся из реестра;
  * студенты базы, которых нет в реестре, УДАЛЯЮТСЯ ПОЛНОСТЬЮ — вместе с их
    отметками посещаемости, периодами отсутствия и членством в группах, а
    ФИО в журнале аудита затирается (необратимо; перед загрузкой сделайте
    копию базы); группы, в которых после этого не осталось студентов,
    помечаются неактивными (сами не удаляются);
  * кураторов и их назначения не трогает.

Без --apply ничего не пишет в базу — только печатает, что было бы сделано.
Идемпотентен: повторный запуск ничего не меняет.

Предохранитель: если файл удалил бы больше 10% студентов базы (и больше 10 человек) — похоже на неполную выгрузку —
загрузка останавливается, ничего не записав. Порог меняется --max-delete-percent, осознанное удаление — --force-delete.
Настройки вместо зашитых значений: дата зачисления новых студентов — --enrolled-at (или IMPORT_ENROLLED_AT);
дополнительные адреса площадок → отделение — JSON-файл {"адрес": "Отделение"} в --addresses (или REGISTRY_ADDRESS_MAP);
результат запуска в файл — --report.

    python -m scripts.import_registry путь/к/реестру.xlsx            # проверка
    python -m scripts.import_registry путь/к/реестру.xlsx --apply    # загрузка

Файл реестра содержит реальные ФИО и даты рождения — держите его вне git
(в базу даты рождения не попадают).
"""
import argparse
import datetime
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.time import today_local
from app.db import base as db_base
from app.models import (
    AbsencePeriod, AttendanceMark, AuditLog, Department, Student, StudentGroupMembership,
    StudentStatus, StudyGroup,
)
from app.services import group_membership_service
from app.services.erasure_service import erase_student_personal_data
from scripts._report import write_report

# Адрес площадки (как в реестре) → отделение.
ADDRESS_TO_DEPARTMENT = {
    "город Москва, улица 1-я Мясниковская, дом 16": "Диджитал",
    "город Москва, улица Расковой, дом 4": "Моссовет",
    "город Москва, улица 1-я Парковая, дом 12": "Датахаб",
    "город Москва, улица Верхняя Первомайская, дом 7": "Техно",
    "город Москва, шоссе Щёлковское, дом 52": "Кибер",
    "город Москва, улица 5-я Парковая, дом 58": "АртТех",
}
STATUS_BY_TEXT = {
    "Обучается": StudentStatus.STUDYING,
    "В академическом отпуске": StudentStatus.ACADEMIC_LEAVE,
}
# Нужные колонки ищутся по названию в строке заголовка — порядок и наличие
# остальных колонок (телефон, почта и т. п.) не важны, и эти данные в базу
# не попадают.
HEADER_FIO, HEADER_STATUS, HEADER_GROUP, HEADER_ADDRESS, HEADER_COURSE = (
    "ФИО", "Статус обучения", "Учебная группа", "Адрес площадки", "Курс обучения",
)
# Дата зачисления для студентов, которых в базе ещё не было, — как у прошлого
# импорта: отметки посещаемости на платформе начинаются с запуска.
ENROLLED_AT = datetime.date.fromisoformat(os.environ.get("IMPORT_ENROLLED_AT") or "2026-09-01")
# Предохранитель на удаление: см. docstring.
GUARD_MIN_ABSENT = 10
DEFAULT_MAX_DELETE_PERCENT = 10.0
# Хвост кода группы в реестре — год набора («-26») или номер подгруппы («.8»):
# на платформе группа называется без него («ИИ112»), а группы, отличавшиеся
# только хвостом, считаются одной.
CODE_SUFFIX = re.compile(r"(-\d{2}|\.\d+)$")


def normalize_code(code: str) -> str:
    return CODE_SUFFIX.sub("", code.strip())


@dataclass(frozen=True)
class RegistryRow:
    last_name: str
    first_name: str
    middle_name: str | None
    status: StudentStatus
    group: str
    department: str
    course: int

    @property
    def fio(self) -> tuple[str, str, str]:
        return (self.last_name, self.first_name, self.middle_name or "")


def load_address_map(path: str | None = None) -> dict[str, str]:
    """Встроенные адреса площадок + дополнительные из JSON-файла (новая площадка не требует правки кода)."""
    result = dict(ADDRESS_TO_DEPARTMENT)
    extra_path = path or os.environ.get("REGISTRY_ADDRESS_MAP")
    if extra_path:
        with open(extra_path, encoding="utf-8") as f:
            extra = json.load(f)
        if not isinstance(extra, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in extra.items()):
            raise RuntimeError(f"{extra_path}: нужен JSON-объект «адрес площадки»: «название отделения»")
        result.update({k.strip(): v.strip() for k, v in extra.items()})
    return result


def read_registry(path: str, address_map: dict[str, str] | None = None) -> list[RegistryRow]:
    address_map = address_map if address_map is not None else ADDRESS_TO_DEPARTMENT
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    needed = (HEADER_FIO, HEADER_STATUS, HEADER_GROUP, HEADER_ADDRESS, HEADER_COURSE)
    header_index = next(
        (i for i, r in enumerate(rows) if all(name in [str(c).strip() for c in r if c is not None] for name in needed)),
        None,
    )
    if header_index is None:
        raise RuntimeError(f"В файле не найдена строка заголовка реестра с колонками: {', '.join(needed)}.")
    titles = [str(c).strip() if c is not None else "" for c in rows[header_index]]
    col_fio, col_status, col_group, col_address, col_course = (titles.index(name) for name in needed)

    result = []
    for number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not row[col_fio]:
            continue
        parts = " ".join(str(row[col_fio]).split()).split(" ")
        if len(parts) < 2:
            raise RuntimeError(f"Строка {number}: в ФИО меньше двух слов — «{row[col_fio]}»")
        status = STATUS_BY_TEXT.get(str(row[col_status]).strip())
        if status is None:
            raise RuntimeError(f"Строка {number}: неизвестный статус обучения «{row[col_status]}»")
        department = address_map.get(str(row[col_address]).strip())
        if department is None:
            raise RuntimeError(f"Строка {number}: неизвестный адрес площадки «{row[col_address]}»")
        course_match = re.match(r"\s*(\d+)", str(row[col_course]))
        if course_match is None or not row[col_group]:
            raise RuntimeError(f"Строка {number}: нет курса или группы")
        result.append(RegistryRow(
            last_name=parts[0], first_name=parts[1], middle_name=" ".join(parts[2:]) or None,
            status=status, group=normalize_code(str(row[col_group])), department=department,
            course=int(course_match.group(1)),
        ))
    return result


def _check_registry(rows: list[RegistryRow]) -> None:
    groups: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for r in rows:
        groups[r.group].add((r.department, r.course))
    broken = {code: sorted(v) for code, v in groups.items() if len(v) > 1}
    if broken:
        raise RuntimeError(f"Группа с разными отделениями/курсами в реестре: {broken}")
    seen = set()
    for r in rows:
        key = (r.group, r.fio)
        if key in seen:
            raise RuntimeError(f"Дубль в реестре: {r.group} — {' '.join(r.fio)}")
        seen.add(key)


def run(
    path: str, apply: bool, today: datetime.date | None = None, *,
    max_delete_percent: float = DEFAULT_MAX_DELETE_PERCENT, force_delete: bool = False,
    enrolled_at: datetime.date | None = None, address_map_file: str | None = None, report: str | None = None,
) -> dict[str, int]:
    today = today or today_local()
    enrolled_at = enrolled_at or ENROLLED_AT
    rows = read_registry(path, load_address_map(address_map_file))
    _check_registry(rows)

    db = db_base.SessionLocal()
    stats: dict[str, int] = defaultdict(int)
    try:
        departments = {d.name: d for d in db.query(Department).all()}
        for name in sorted({r.department for r in rows}):
            if name not in departments:
                departments[name] = Department(name=name)
                db.add(departments[name])
                db.flush()
                stats["отделений создано"] += 1
                print(f"+ отделение {name}")

        registry_groups: dict[str, list[RegistryRow]] = defaultdict(list)
        for r in rows:
            registry_groups[r.group].append(r)

        groups = {g.code: g for g in db.query(StudyGroup).all()}
        students = db.query(Student).all()
        students_by_group: dict[int, list[Student]] = defaultdict(list)
        for s in students:
            students_by_group[s.study_group_id].append(s)

        # ---- группы ----
        # Код на платформе — без хвоста реестра. Основная группа: уже имеющая
        # такой код, иначе самая многочисленная из групп, отличавшихся от него
        # только хвостом («ИИ112-26», «ИИ112.8»), — её переименовываем. Остальные
        # такие группы опустеют (их студентов ниже переведёт в основную по ФИО)
        # и будут скрыты.
        by_normalized: dict[str, list[StudyGroup]] = defaultdict(list)
        for g in groups.values():
            by_normalized[normalize_code(g.code)].append(g)
        for code, members in sorted(registry_groups.items()):
            department = departments[members[0].department]
            course = members[0].course
            if code not in groups:
                candidates = sorted(
                    by_normalized.get(code, []),
                    key=lambda g: (-len(students_by_group[g.id]), g.code),
                )
                if candidates:
                    primary = candidates[0]
                    print(f"~ группа {primary.code} → {code}")
                    del groups[primary.code]
                    primary.code = code
                    groups[code] = primary
                    stats["групп переименовано"] += 1
                else:
                    groups[code] = StudyGroup(code=code, course=course, department_id=department.id)
                    db.add(groups[code])
                    stats["групп создано"] += 1
            group = groups[code]
            if group.course != course:
                group.course = course
                stats["курс группы изменён"] += 1
            if group.department_id != department.id:
                print(f"~ группа {code}: отделение → {department.name}")
                group.department_id = department.id
                stats["отделение группы изменено"] += 1
            if group.is_active is False:
                group.is_active = True
                stats["групп возвращено в работу"] += 1
        db.flush()

        # ---- студенты ----
        def key(s: Student) -> tuple[str, str, str]:
            return (s.last_name, s.first_name, s.middle_name or "")

        matched: dict[int, RegistryRow] = {}  # id студента → строка реестра
        unmatched_rows: list[RegistryRow] = []
        for code, members in registry_groups.items():
            pool: dict[tuple[str, str, str], list[Student]] = defaultdict(list)
            for s in students_by_group[groups[code].id]:
                pool[key(s)].append(s)
            for r in members:
                candidates = [s for s in pool[r.fio] if s.id not in matched]
                if candidates:
                    # Предпочитаем действующую запись выбывшей.
                    candidates.sort(key=lambda s: s.status == StudentStatus.EXPELLED)
                    matched[candidates[0].id] = r
                else:
                    unmatched_rows.append(r)

        free_by_fio: dict[tuple[str, str, str], list[Student]] = defaultdict(list)
        for s in students:
            if s.id not in matched:
                free_by_fio[key(s)].append(s)

        for r in unmatched_rows:
            candidates = [s for s in free_by_fio[r.fio] if s.id not in matched]
            if len(candidates) == 1:
                matched[candidates[0].id] = r
                continue
            student = Student(
                last_name=r.last_name, first_name=r.first_name, middle_name=r.middle_name,
                study_group_id=groups[r.group].id, status=r.status, enrolled_at=enrolled_at,
            )
            db.add(student)
            db.flush()
            group_membership_service.create_initial_membership(db, student)
            stats["студентов создано"] += 1

        by_id = {s.id: s for s in students}
        for student_id, r in matched.items():
            student = by_id[student_id]
            target_id = groups[r.group].id
            if student.study_group_id != target_id:
                group_membership_service.transfer_student(db, student, target_id, today, None)
                student.study_group_id = target_id
                stats["студентов переведено"] += 1
            if student.status != r.status or student.left_at is not None:
                if student.status == StudentStatus.EXPELLED:
                    stats["студентов возвращено из выбывших"] += 1
                student.status = r.status
                student.left_at = None
                stats["статус студента изменён"] += 1

        absent_ids = [s.id for s in students if s.id not in matched]
        share = 100 * len(absent_ids) / len(students) if students else 0.0
        if not force_delete and len(absent_ids) > GUARD_MIN_ABSENT and share > max_delete_percent:
            raise RuntimeError(
                f"Файл удалил бы {len(absent_ids)} из {len(students)} студентов базы ({share:.0f}%, предел {max_delete_percent:g}%) — "
                "похоже на неполную выгрузку реестра. Ничего не записано. Проверьте файл; если удаление "
                "действительно нужно — запустите с --force-delete (и сначала сделайте копию БД)."
            )
        for start in range(0, len(absent_ids), 500):
            chunk = absent_ids[start:start + 500]
            marks_deleted = db.query(AttendanceMark).filter(
                AttendanceMark.student_id.in_(chunk)).delete(synchronize_session=False)
            if marks_deleted:
                stats["отметок посещаемости удалено"] += marks_deleted
            db.query(AbsencePeriod).filter(AbsencePeriod.student_id.in_(chunk)).delete(synchronize_session=False)
            db.query(StudentGroupMembership).filter(
                StudentGroupMembership.student_id.in_(chunk)).delete(synchronize_session=False)
            erase_student_personal_data(db, chunk, include_access_log=True)
            db.query(AuditLog).filter(
                AuditLog.entity_type == "student", AuditLog.entity_id.in_([str(i) for i in chunk])
            ).update({"old_value": "[обезличено]", "new_value": "[обезличено]"}, synchronize_session=False)
            db.query(Student).filter(Student.id.in_(chunk)).delete(synchronize_session=False)
        if absent_ids:
            stats["студентов удалено (нет в реестре)"] += len(absent_ids)
        db.flush()

        # Группа без единого действующего студента (и без студентов в реестре)
        # больше не работает — скрываем, не удаляя историю.
        active_by_group: dict[int, int] = defaultdict(int)
        for s in db.query(Student):
            active_by_group[s.study_group_id] += 1
        for code, group in sorted(groups.items()):
            if code in registry_groups or not group.is_active or active_by_group[group.id]:
                continue
            group.is_active = False
            stats["групп скрыто (нет студентов)"] += 1
            print(f"- группа {code} без студентов — скрыта")
        for code, group in sorted(groups.items()):
            if code not in registry_groups and group.is_active:
                print(f"! группы {code} нет в реестре, но в ней есть студенты — оставлена")

        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    write_report(report, "Загрузка реестра контингента", apply, stats)
    print(("Загружено." if apply else "Проверка (ничего не записано; добавьте --apply):"))
    for name, count in stats.items():
        print(f"  {name}: {count}")
    print(f"  всего строк в реестре: {len(rows)}, групп: {len(registry_groups)}")
    return dict(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="файл реестра контингента (.xlsx)")
    parser.add_argument("--apply", action="store_true", help="записать изменения в базу")
    parser.add_argument("--max-delete-percent", type=float, default=DEFAULT_MAX_DELETE_PERCENT,
                        help="предохранитель: больше этой доли студентов не удалять (по умолчанию 10)")
    parser.add_argument("--force-delete", action="store_true", help="снять предохранитель на удаление")
    parser.add_argument("--enrolled-at", type=datetime.date.fromisoformat, help="дата зачисления новых студентов, ГГГГ-ММ-ДД")
    parser.add_argument("--addresses", metavar="ФАЙЛ.json", help="дополнительные адреса площадок → отделение")
    parser.add_argument("--report", metavar="ФАЙЛ.txt", help="сохранить результат запуска в файл")
    args = parser.parse_args()
    try:
        run(args.path, args.apply, max_delete_percent=args.max_delete_percent, force_delete=args.force_delete,
            enrolled_at=args.enrolled_at, address_map_file=args.addresses, report=args.report)
    except RuntimeError as exc:
        sys.exit(f"Ошибка: {exc}")


if __name__ == "__main__":
    main()
