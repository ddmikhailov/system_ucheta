"""Импорт групп, кураторов и студентов «Диджитал» из выгрузок трёх файлов
Яндекс.Таблиц за сентябрь 2026 (data/groups.csv, curators.csv, students.csv).

Отметки посещаемости за сентябрь сознательно не переносятся — attendance_marks
стартует пустой, первая сдача дня будет с даты запуска платформы (см. концепцию,
раздел «Открытые вопросы»).

Идемпотентен: повторный запуск не создаёт дублей группы/студента/пользователя.

    python -m scripts.seed
    python -m scripts.import_source_data
"""
import csv
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import base as db_base
from app.models import (
    AssignmentRole,
    CuratorAssignment,
    Department,
    Role,
    RoleCode,
    Student,
    StudyGroup,
    User,
)

# На сервере CSV с реальными ФИО лежат не в репозитории (он публичный), а в
# постоянном хранилище — путь задаётся IMPORT_DATA_DIR.
DATA_DIR = os.environ.get("IMPORT_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "import", "data"
)
PILOT_DEPARTMENT_NAME = "Диджитал"

# Дата начала занятий по заголовку исходных таблиц ("2026-09-01" в шапке ИТОГ).
ENROLLED_AT = datetime.date(2026, 9, 1)

VACANCY_MARKER = "Вакансия тьютор"


def _read_csv(name: str) -> list[dict]:
    with open(os.path.join(DATA_DIR, name), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run() -> None:
    db = db_base.SessionLocal()
    try:
        department = db.query(Department).filter(Department.name == PILOT_DEPARTMENT_NAME).one_or_none()
        if department is None:
            raise RuntimeError(
                f"Отделение «{PILOT_DEPARTMENT_NAME}» не найдено — сначала запустите scripts.seed"
            )
        curator_role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one_or_none()
        if curator_role is None:
            raise RuntimeError("Роль curator не найдена — сначала запустите scripts.seed")

        curators_rows = _read_csv("curators.csv")
        username_by_full_name: dict[str, str] = {}
        created_users = 0
        for row in curators_rows:
            full_name = row["full_name"]
            username_by_full_name[full_name] = row["username"]
            user = db.query(User).filter(User.username == row["username"]).one_or_none()
            if user is None:
                user = User(
                    username=row["username"],
                    full_name=full_name,
                    role_id=curator_role.id,
                    department_id=department.id,
                    password_hash=None,
                )
                db.add(user)
                created_users += 1
        db.commit()
        print(f"+ кураторов создано: {created_users} (всего в файле: {len(curators_rows)})")

        users_by_username = {
            u.username: u for u in db.query(User).filter(User.username.in_(username_by_full_name.values()))
        }

        groups_rows = _read_csv("groups.csv")
        group_by_code: dict[str, StudyGroup] = {}
        created_groups = 0
        for row in groups_rows:
            code = row["code"]
            group = db.query(StudyGroup).filter(StudyGroup.code == code).one_or_none()
            if group is None:
                group = StudyGroup(code=code, course=int(row["course"]), department_id=department.id)
                db.add(group)
                db.flush()
                created_groups += 1
            group_by_code[code] = group
        db.commit()
        print(f"+ групп создано: {created_groups} (всего в файле: {len(groups_rows)})")

        created_assignments = 0
        for row in groups_rows:
            curator_full_name = row["curator"]
            if curator_full_name == VACANCY_MARKER:
                continue
            username = username_by_full_name.get(curator_full_name)
            user = users_by_username.get(username) if username else None
            if user is None:
                print(f"! куратор «{curator_full_name}» не найден для группы {row['code']}, пропуск")
                continue

            group = group_by_code[row["code"]]
            existing = (
                db.query(CuratorAssignment)
                .filter(
                    CuratorAssignment.study_group_id == group.id,
                    CuratorAssignment.user_id == user.id,
                    CuratorAssignment.role_type == AssignmentRole.CURATOR,
                )
                .one_or_none()
            )
            if existing is None:
                db.add(
                    CuratorAssignment(
                        study_group_id=group.id, user_id=user.id,
                        role_type=AssignmentRole.CURATOR, start_date=ENROLLED_AT,
                    )
                )
                created_assignments += 1
        db.commit()
        print(f"+ назначений куратор-группа создано: {created_assignments}")

        students_rows = _read_csv("students.csv")
        created_students = 0
        for row in students_rows:
            group = group_by_code.get(row["group"])
            if group is None:
                print(f"! группа {row['group']} не найдена для студента {row['full_name_raw']}, пропуск")
                continue

            existing = (
                db.query(Student)
                .filter(
                    Student.study_group_id == group.id,
                    Student.last_name == row["last_name"],
                    Student.first_name == row["first_name"],
                    Student.middle_name == (row["middle_name"] or None),
                )
                .first()
            )
            if existing is not None:
                continue

            db.add(
                Student(
                    last_name=row["last_name"],
                    first_name=row["first_name"],
                    middle_name=row["middle_name"] or None,
                    study_group_id=group.id,
                    enrolled_at=ENROLLED_AT,
                )
            )
            created_students += 1
        db.commit()
        print(f"+ студентов создано: {created_students} (всего в файле: {len(students_rows)})")

        print("Готово. Группы без куратора (нужна ручная привязка зав. отделением):")
        for row in groups_rows:
            if row["curator"] == VACANCY_MARKER:
                print(f"  - {row['code']}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
