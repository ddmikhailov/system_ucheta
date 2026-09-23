"""Справочные данные, без которых система не работает: роли, коды отметок,
отделение пилота и учётная запись администратора.

Идемпотентен — можно запускать повторно, существующие записи не дублируются.

    python -m scripts.seed
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password
from app.db import base as db_base
from app.models import Department, MarkCode, Role, RoleCode, User

PILOT_DEPARTMENT_NAME = "Диджитал"

ROLES = [
    (RoleCode.CURATOR, "Куратор"),
    (RoleCode.DEPUTY_CURATOR, "Заместитель куратора"),
    (RoleCode.DEPT_HEAD, "Заведующий отделением"),
    (RoleCode.EDU_DEPARTMENT, "Воспитательный отдел"),
    (RoleCode.ADMIN, "Администратор"),
    (RoleCode.TUTOR, "Тьютор"),
]

# Флаги закреплены здесь один раз — дальше их можно менять из админки без правки кода.
MARK_CODES = [
    ("о", "Опоздание", True, False, False),
    ("и", "ИУП", False, True, True),
    ("б", "Больничный лист", False, True, True),
    ("з", "Заявление", False, True, True),
    ("п", "По приказу", False, True, True),
    ("р", "Производственная практика", False, True, True),
    ("у", "Ушёл с занятий", False, False, False),
    ("н", "Неуважительная причина", False, False, False),
]


def run() -> None:
    db = db_base.SessionLocal()
    try:
        roles_by_code = {}
        for code, name in ROLES:
            role = db.query(Role).filter(Role.code == code.value).one_or_none()
            if role is None:
                role = Role(code=code.value, name=name)
                db.add(role)
                db.flush()
                print(f"+ роль {code.value}")
            roles_by_code[code] = role

        for idx, (code, name, counts_as_present, is_excused, requires_document) in enumerate(MARK_CODES, start=1):
            existing = db.query(MarkCode).filter(MarkCode.code == code).one_or_none()
            if existing is None:
                db.add(
                    MarkCode(
                        code=code, name=name, counts_as_present=counts_as_present,
                        is_excused=is_excused, requires_document=requires_document, sort_order=idx,
                    )
                )
                print(f"+ код отметки {code} — {name}")

        department = db.query(Department).filter(Department.name == PILOT_DEPARTMENT_NAME).one_or_none()
        if department is None:
            department = Department(name=PILOT_DEPARTMENT_NAME)
            db.add(department)
            db.flush()
            print(f"+ отделение {PILOT_DEPARTMENT_NAME}")

        db.commit()

        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin = db.query(User).filter(User.username == admin_username).one_or_none()
        if admin is None:
            admin_password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            admin = User(
                username=admin_username,
                full_name="Администратор",
                role_id=roles_by_code[RoleCode.ADMIN].id,
                password_hash=hash_password(admin_password),
            )
            db.add(admin)
            db.commit()
            print(f"+ администратор создан: логин={admin_username}, пароль={admin_password}")
            print("  Смените пароль после первого входа.")
        else:
            print(f"= администратор {admin_username} уже существует")

        print("Готово.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
