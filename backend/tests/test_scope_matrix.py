"""Зона видимости: роль × отделение × группа × чтение/запись. Ожидания сняты с проверок,
как они работали до появления scope_of (deps.assert_can_access_group/assert_can_view_group,
scope_department_id, policies.assert_can_manage_group/student, passport_service.accessible_groups,
meal_service.visible_groups) — после перевода на scope_of ни одна строка здесь не должна меняться.

Отделение A — «своё», B — «чужое». Куратор, заместитель, соц. педагог и психолог числятся в
отделении B, а ведут группу из A: видимость «по группам» определяется назначением, а не отделением."""
import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps
from app.core import policies, roles
from app.core.roles import ScopeKind
from app.core.security import hash_password
from app.core.time import today_local
from app.models import CuratorAssignment, Department, Role, RoleCode, Student, StudyGroup, User
from app.models.enums import AssignmentRole
from app.services import meal_service, passport_service

A, B = "A", "B"
NO_DEPT = None

# (роль, отделение пользователя, ведёт ли группу A)
PEOPLE = {
    "admin": (RoleCode.ADMIN, NO_DEPT, False),
    "dept_head": (RoleCode.DEPT_HEAD, A, False),
    "tutor": (RoleCode.TUTOR, A, False),
    "edu": (RoleCode.EDU_DEPARTMENT, A, False),
    "dept_head_nodept": (RoleCode.DEPT_HEAD, NO_DEPT, False),
    "edu_nodept": (RoleCode.EDU_DEPARTMENT, NO_DEPT, False),
    "social": (RoleCode.SOCIAL_PEDAGOGUE, B, True),
    "psych": (RoleCode.PSYCHOLOGIST, B, True),
    "curator": (RoleCode.CURATOR, B, True),
    "deputy": (RoleCode.DEPUTY_CURATOR, B, True),
    "curator_idle": (RoleCode.CURATOR, A, False),  # в отделении A, но групп не ведёт
    "meal": (RoleCode.MEAL_MANAGER, NO_DEPT, False),
}

# кто: (видит A, видит B, пишет в A, пишет в B)
GROUP_ACCESS = {
    "admin": (True, True, True, True),
    "dept_head": (True, False, True, False),
    "tutor": (True, False, True, False),
    "edu": (True, False, True, False),
    "dept_head_nodept": (False, False, False, False),
    "edu_nodept": (False, False, False, False),
    "social": (True, True, True, False),
    "psych": (True, True, True, False),
    "curator": (True, False, True, False),
    "deputy": (True, False, True, False),
    "curator_idle": (False, False, False, False),
    "meal": (False, False, False, False),
}

# scope_department_id(user, запрошенное): "own" — своё отделение, "asked" — что запросили, 403 — отказ
DEPARTMENT_FILTER = {
    "admin": "asked", "dept_head": "own", "tutor": "own", "edu": "own",
    "dept_head_nodept": 403, "edu_nodept": 403,
    "social": "asked", "psych": "asked", "curator": "asked", "deputy": "asked", "curator_idle": "asked",
    "meal": "asked",
}

# assert_can_manage_group / assert_can_manage_student: (группа/студент A, группа/студент B). Это проверка
# только отделения: кого вообще пускать к управлению, решают ролевые зависимости эндпоинтов.
MANAGE = {
    "admin": (True, True), "dept_head": (True, False), "tutor": (True, False), "edu": (True, False),
    "dept_head_nodept": (False, False), "edu_nodept": (False, False),
    "social": (True, True), "psych": (True, True), "curator": (True, True), "deputy": (True, True),
    "curator_idle": (True, True), "meal": (True, True),
}

# Паспорт группы: какие из групп A/B есть в списке доступных.
PASSPORT = {
    "admin": {A, B}, "dept_head": {A}, "tutor": {A}, "edu": {A},
    "dept_head_nodept": set(), "edu_nodept": set(),
    "social": {A, B}, "psych": {A, B}, "curator": {A}, "deputy": {A}, "curator_idle": set(), "meal": set(),
}

# Свод питания без запрошенного отделения и с запрошенным B.
MEALS = {
    "admin": ({A, B}, {B}), "dept_head": ({A}, {A}), "tutor": ({A}, {A}), "edu": ({A}, {A}),
    "dept_head_nodept": (set(), set()), "edu_nodept": (set(), set()),
    "social": ({A, B}, {B}), "psych": ({A, B}, {B}), "curator": ({A, B}, {B}), "deputy": ({A, B}, {B}),
    "curator_idle": ({A, B}, {B}), "meal": ({A, B}, {B}),
}


@pytest.fixture()
def world(db, seeded):
    dept_a = Department(name="Отделение А (тест зон)")
    dept_b = Department(name="Отделение Б (тест зон)")
    db.add_all([dept_a, dept_b])
    db.flush()
    depts = {A: dept_a, B: dept_b}
    groups = {
        A: StudyGroup(code="ЗОНА-А1", course=1, department_id=dept_a.id),
        B: StudyGroup(code="ЗОНА-Б1", course=1, department_id=dept_b.id),
    }
    db.add_all(groups.values())
    db.flush()
    students = {
        key: Student(last_name="Тестов", first_name=f"Студент{key}", study_group_id=g.id,
                     enrolled_at=datetime.date(2020, 9, 1))
        for key, g in groups.items()
    }
    db.add_all(students.values())
    role_ids = {r.code: r.id for r in db.query(Role).all()}
    users = {}
    for name, (role, dept, leads_a) in PEOPLE.items():
        user = User(username=f"zone_{name}", full_name=f"Тест {name}", role_id=role_ids[role.value],
                    department_id=depts[dept].id if dept else None, password_hash=hash_password("Zone#Test58x!"))
        db.add(user)
        db.flush()
        if leads_a:
            db.add(CuratorAssignment(study_group_id=groups[A].id, user_id=user.id,
                                     role_type=AssignmentRole.CURATOR, start_date=datetime.date(2020, 9, 1)))
        users[name] = user
    db.commit()
    return {"users": users, "groups": groups, "students": students, "depts": depts}


def _allowed(fn) -> bool:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == 403
        return False
    return True


@pytest.mark.parametrize("name", PEOPLE)
def test_group_view_and_edit(db, world, name):
    user, groups, today = world["users"][name], world["groups"], today_local()
    got = (
        _allowed(lambda: deps.assert_can_view_group(db, user, groups[A].id, today)),
        _allowed(lambda: deps.assert_can_view_group(db, user, groups[B].id, today)),
        _allowed(lambda: deps.assert_can_access_group(db, user, groups[A].id, today)),
        _allowed(lambda: deps.assert_can_access_group(db, user, groups[B].id, today)),
    )
    assert got == GROUP_ACCESS[name]


@pytest.mark.parametrize("name", PEOPLE)
def test_department_filter(world, name):
    user, depts = world["users"][name], world["depts"]
    expected = DEPARTMENT_FILTER[name]
    for asked in (None, depts[B].id):
        if expected == 403:
            with pytest.raises(HTTPException) as exc:
                deps.scope_department_id(user, asked)
            assert exc.value.status_code == 403
        elif expected == "own":
            assert deps.scope_department_id(user, asked) == user.department_id
        else:
            assert deps.scope_department_id(user, asked) == asked


@pytest.mark.parametrize("name", PEOPLE)
def test_manage_group_and_student(db, world, name):
    user, groups, students = world["users"][name], world["groups"], world["students"]
    assert (
        _allowed(lambda: policies.assert_can_manage_group(user, groups[A])),
        _allowed(lambda: policies.assert_can_manage_group(user, groups[B])),
    ) == MANAGE[name]
    assert (
        _allowed(lambda: policies.assert_can_manage_student(db, user, students[A])),
        _allowed(lambda: policies.assert_can_manage_student(db, user, students[B])),
    ) == MANAGE[name]


def _keys(world, groups) -> set[str]:
    ids = {g.id for g in groups}
    return {key for key, g in world["groups"].items() if g.id in ids}


@pytest.mark.parametrize("name", PEOPLE)
def test_passport_groups(db, world, name):
    assert _keys(world, passport_service.accessible_groups(db, world["users"][name])) == PASSPORT[name]


@pytest.mark.parametrize("name", PEOPLE)
def test_meal_groups(db, world, name):
    user = world["users"][name]
    got = (
        _keys(world, meal_service.visible_groups(db, user)),
        _keys(world, meal_service.visible_groups(db, user, world["depts"][B].id)),
    )
    assert got == MEALS[name]


def test_every_role_is_in_the_matrix():
    assert {role for role, _, _ in PEOPLE.values()} == set(RoleCode)
    assert set(roles.ROLE_SCOPES) == set(RoleCode)  # у новой роли зона задаётся явно


def test_routers_and_services_ask_the_scope_not_the_role_groups():
    """Сторож: роутеры и сервисы спрашивают зону (policies.scope_of / deps.assert_can_*), а не перебирают
    группы ролей сами — иначе разброс проверок, из-за которого права расходились, вернётся."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in [*(app_dir / "api" / "routers").rglob("*.py"), *(app_dir / "services").rglob("*.py")]:
        text = path.read_text(encoding="utf-8")
        for name in ("DEPARTMENT_SCOPED_ROLES", "COLLEGE_WIDE_ROLES", "DOSSIER_STAFF_ROLES"):
            if name in text:
                offenders.append(f"{path.relative_to(app_dir)}: {name}")
    assert offenders == []


@pytest.mark.parametrize("role", list(RoleCode))
def test_scope_of_matches_the_role_table(role):
    user = SimpleNamespace(id=7, role=SimpleNamespace(code=role.value), department_id=3)
    view, edit = roles.ROLE_SCOPES[role]
    assert policies.scope_of(user, "view").kind is view
    assert policies.scope_of(user, "edit").kind is edit
    if view is ScopeKind.DEPARTMENT:
        assert policies.scope_of(user).department_id == 3
