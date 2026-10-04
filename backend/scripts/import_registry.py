"""Загрузка реестра контингента колледжа (выгрузка xlsx) — группы и студенты
всех отделений.

Что делает:
  * отделение определяется по адресу площадки (ADDRESS_TO_DEPARTMENT), нужных
    отделений, которых ещё нет, заводит;
  * группы: совпадение по коду; если в базе группа ещё под старым кодом без
    года («ИИ112» → «ИИ112-26»), она переименовывается — вместе с кураторами,
    историей и отметками (переименование разрешено, только если у старой
    группы есть общие студенты с новой, иначе это просто разные группы);
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

    python -m scripts.import_registry путь/к/реестру.xlsx            # проверка
    python -m scripts.import_registry путь/к/реестру.xlsx --apply    # загрузка

Файл реестра содержит реальные ФИО и даты рождения — держите его вне git
(в базу даты рождения не попадают).
"""
import argparse
import datetime
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
EXPECTED_HEADER = ("ФИО", "Дата рождения", "Пол", "Статус обучения")
# Колонки реестра (после строки заголовка): ФИО, …, статус, …, группа, адрес, курс.
COL_FIO, COL_STATUS, COL_GROUP, COL_ADDRESS, COL_COURSE = 0, 3, 6, 7, 8
# Дата зачисления для студентов, которых в базе ещё не было, — как у прошлого
# импорта: отметки посещаемости на платформе начинаются с запуска.
ENROLLED_AT = datetime.date(2026, 9, 1)
# Старый код группы + «-26» (год набора) = код в реестре.
LEGACY_SUFFIX = re.compile(r"-\d{2}")


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


def read_registry(path: str) -> list[RegistryRow]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    header_index = next(
        (i for i, r in enumerate(rows) if tuple(r[: len(EXPECTED_HEADER)]) == EXPECTED_HEADER), None
    )
    if header_index is None:
        raise RuntimeError("В файле не найдена строка заголовка реестра (ФИО, Дата рождения, Пол, …).")

    result = []
    for number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not row[COL_FIO]:
            continue
        parts = " ".join(str(row[COL_FIO]).split()).split(" ")
        if len(parts) < 2:
            raise RuntimeError(f"Строка {number}: в ФИО меньше двух слов — «{row[COL_FIO]}»")
        status = STATUS_BY_TEXT.get(str(row[COL_STATUS]).strip())
        if status is None:
            raise RuntimeError(f"Строка {number}: неизвестный статус обучения «{row[COL_STATUS]}»")
        department = ADDRESS_TO_DEPARTMENT.get(str(row[COL_ADDRESS]).strip())
        if department is None:
            raise RuntimeError(f"Строка {number}: неизвестный адрес площадки «{row[COL_ADDRESS]}»")
        course_match = re.match(r"\s*(\d+)", str(row[COL_COURSE]))
        if course_match is None or not row[COL_GROUP]:
            raise RuntimeError(f"Строка {number}: нет курса или группы")
        result.append(RegistryRow(
            last_name=parts[0], first_name=parts[1], middle_name=" ".join(parts[2:]) or None,
            status=status, group=str(row[COL_GROUP]).strip(), department=department,
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


def run(path: str, apply: bool, today: datetime.date | None = None) -> dict[str, int]:
    today = today or today_local()
    rows = read_registry(path)
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
        claimed = {code for code in registry_groups if code in groups}
        for code, members in sorted(registry_groups.items()):
            department = departments[members[0].department]
            course = members[0].course
            if code not in groups:
                names = {r.fio for r in members}
                legacy = next(
                    (
                        g for old_code, g in sorted(groups.items())
                        if old_code not in claimed and old_code not in registry_groups
                        and code.startswith(old_code) and LEGACY_SUFFIX.fullmatch(code[len(old_code):])
                        and any((s.last_name, s.first_name, s.middle_name or "") in names
                                for s in students_by_group[g.id])
                    ),
                    None,
                )
                if legacy is not None:
                    print(f"~ группа {legacy.code} → {code}")
                    del groups[legacy.code]
                    legacy.code = code
                    groups[code] = legacy
                    claimed.add(code)
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
                study_group_id=groups[r.group].id, status=r.status, enrolled_at=ENROLLED_AT,
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

    print(("Загружено." if apply else "Проверка (ничего не записано; добавьте --apply):"))
    for name, count in stats.items():
        print(f"  {name}: {count}")
    print(f"  всего строк в реестре: {len(rows)}, групп: {len(registry_groups)}")
    return dict(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="файл реестра контингента (.xlsx)")
    parser.add_argument("--apply", action="store_true", help="записать изменения в базу")
    args = parser.parse_args()
    run(args.path, args.apply)


if __name__ == "__main__":
    main()
