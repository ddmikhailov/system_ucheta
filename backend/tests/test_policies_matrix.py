"""Матрица «роль × действие × отделение» для app.core.policies (см. TODO.md 5:
раньше эта логика была размазана по admin.py без единого места, которое
можно было бы вот так перебрать целиком). Тестовые двойники — простые
объекты с нужными атрибутами, без БД: сами правила чистые функции над
role.code/department_id/id, реальная модель им не нужна."""
from types import SimpleNamespace

import pytest

from app.core import policies

ADMIN = "admin"
TUTOR = "tutor"
DEPT_HEAD = "dept_head"
EDU_DEPARTMENT = "edu_department"
CURATOR = "curator"
DEPUTY_CURATOR = "deputy_curator"

DEPT_A = 1
DEPT_B = 2


def _user(role_code: str, department_id: int | None = None, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=SimpleNamespace(code=role_code), department_id=department_id)


# --- assert_can_manage_user: роль актёра × роль/отделение цели ---

MANAGE_USER_CASES = [
    # (роль актёра, отделение актёра, роль цели, отделение цели, можно ли)
    (ADMIN, None, ADMIN, None, True),
    (ADMIN, None, TUTOR, None, True),
    (ADMIN, None, CURATOR, DEPT_A, True),
    (TUTOR, DEPT_A, CURATOR, DEPT_A, True),  # тьютор — полный доступ, но к своему отделению
    (TUTOR, DEPT_A, CURATOR, DEPT_B, False),
    (TUTOR, DEPT_A, ADMIN, None, False),
    (TUTOR, DEPT_A, TUTOR, DEPT_A, False),
    (TUTOR, DEPT_A, DEPT_HEAD, DEPT_A, False),
    (TUTOR, None, CURATOR, DEPT_A, False),  # у самого нет отделения
    (DEPT_HEAD, DEPT_A, CURATOR, DEPT_A, True),
    (DEPT_HEAD, DEPT_A, DEPUTY_CURATOR, DEPT_A, True),
    (DEPT_HEAD, DEPT_A, CURATOR, DEPT_B, False),  # чужое отделение
    (DEPT_HEAD, DEPT_A, DEPT_HEAD, DEPT_A, False),  # не может управлять другим зав. отделением
    (DEPT_HEAD, DEPT_A, ADMIN, None, False),
    (DEPT_HEAD, None, CURATOR, DEPT_A, False),  # у самого нет отделения
    (EDU_DEPARTMENT, None, CURATOR, DEPT_A, False),  # не управляет учётками вообще
]


@pytest.mark.parametrize("actor_role,actor_dept,target_role,target_dept,allowed", MANAGE_USER_CASES)
def test_assert_can_manage_user_matrix(actor_role, actor_dept, target_role, target_dept, allowed):
    actor = _user(actor_role, actor_dept, user_id=1)
    target = _user(target_role, target_dept, user_id=2)
    if allowed:
        policies.assert_can_manage_user(actor, target)
    else:
        with pytest.raises(Exception):
            policies.assert_can_manage_user(actor, target)


def test_assert_can_manage_user_self_always_allowed_regardless_of_role():
    for role in (ADMIN, TUTOR, DEPT_HEAD, EDU_DEPARTMENT, CURATOR):
        user = _user(role, DEPT_A, user_id=42)
        policies.assert_can_manage_user(user, user)


# --- assert_can_assign_role ---

ASSIGN_ROLE_CASES = [
    (ADMIN, ADMIN, True),
    (ADMIN, EDU_DEPARTMENT, True),
    (DEPT_HEAD, CURATOR, True),
    (DEPT_HEAD, DEPUTY_CURATOR, True),
    (DEPT_HEAD, DEPT_HEAD, True),
    (DEPT_HEAD, ADMIN, False),
    (DEPT_HEAD, TUTOR, False),
    (DEPT_HEAD, EDU_DEPARTMENT, False),
    (TUTOR, CURATOR, True),
    (TUTOR, DEPT_HEAD, False),
    (TUTOR, ADMIN, False),
    (EDU_DEPARTMENT, CURATOR, False),
]


@pytest.mark.parametrize("actor_role,new_role,allowed", ASSIGN_ROLE_CASES)
def test_assert_can_assign_role_matrix(actor_role, new_role, allowed):
    actor = _user(actor_role, DEPT_A)
    if allowed:
        policies.assert_can_assign_role(actor, new_role)
    else:
        with pytest.raises(Exception):
            policies.assert_can_assign_role(actor, new_role)


# --- resolve_department_for_role ---

RESOLVE_DEPARTMENT_CASES = [
    (ADMIN, None, None),
    (ADMIN, DEPT_A, None),  # роль запрещает отделение — молча обнуляется
    (TUTOR, DEPT_A, DEPT_A),
    (EDU_DEPARTMENT, DEPT_A, None),
    (DEPT_HEAD, DEPT_A, DEPT_A),
    (CURATOR, DEPT_A, DEPT_A),
    (DEPUTY_CURATOR, DEPT_A, DEPT_A),
]


@pytest.mark.parametrize("role,requested,expected", RESOLVE_DEPARTMENT_CASES)
def test_resolve_department_for_role_matrix(role, requested, expected):
    assert policies.resolve_department_for_role(role, requested) == expected


@pytest.mark.parametrize("role", [DEPT_HEAD, TUTOR, CURATOR, DEPUTY_CURATOR])
def test_resolve_department_for_role_requires_department_when_missing(role):
    with pytest.raises(Exception):
        policies.resolve_department_for_role(role, None)


# --- assert_can_manage_group ---

MANAGE_GROUP_CASES = [
    (ADMIN, None, DEPT_A, True),
    (TUTOR, DEPT_A, DEPT_A, True),
    (TUTOR, DEPT_A, DEPT_B, False),
    (EDU_DEPARTMENT, None, DEPT_A, True),
    (DEPT_HEAD, DEPT_A, DEPT_A, True),
    (DEPT_HEAD, DEPT_A, DEPT_B, False),
]


@pytest.mark.parametrize("actor_role,actor_dept,group_dept,allowed", MANAGE_GROUP_CASES)
def test_assert_can_manage_group_matrix(actor_role, actor_dept, group_dept, allowed):
    actor = _user(actor_role, actor_dept)
    group = SimpleNamespace(department_id=group_dept)
    if allowed:
        policies.assert_can_manage_group(actor, group)
    else:
        with pytest.raises(Exception):
            policies.assert_can_manage_group(actor, group)


# --- assert_can_manage_student ---


class _FakeDb:
    def __init__(self, group):
        self._group = group

    def get(self, _model, _id):
        return self._group


MANAGE_STUDENT_CASES = [
    (ADMIN, None, DEPT_A, True),
    (TUTOR, DEPT_A, DEPT_A, True),
    (TUTOR, DEPT_A, DEPT_B, False),
    (EDU_DEPARTMENT, None, DEPT_A, True),
    (DEPT_HEAD, DEPT_A, DEPT_A, True),
    (DEPT_HEAD, DEPT_A, DEPT_B, False),
]


@pytest.mark.parametrize("actor_role,actor_dept,student_group_dept,allowed", MANAGE_STUDENT_CASES)
def test_assert_can_manage_student_matrix(actor_role, actor_dept, student_group_dept, allowed):
    actor = _user(actor_role, actor_dept)
    group = SimpleNamespace(department_id=student_group_dept)
    student = SimpleNamespace(study_group_id=1)
    db = _FakeDb(group)
    if allowed:
        policies.assert_can_manage_student(db, actor, student)
    else:
        with pytest.raises(Exception):
            policies.assert_can_manage_student(db, actor, student)
