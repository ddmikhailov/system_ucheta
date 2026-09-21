"""Зав. отделением видит и меняет только своё отделение — эти правки были
реальным пробелом (GET /admin/groups и /admin/users не были ограничены),
найденным при подготовке экрана «вакантные группы» для зав. отделением."""
import datetime

import pytest

from app.core.security import hash_password
from app.models import Department, Role, RoleCode, StudyGroup, User


@pytest.fixture()
def other_department_setup(db, imported, dept_head_user):
    """Второе отделение с одной вакантной группой и своим куратором —
    чтобы было что скрывать от зав. отделением «Диджитал»."""
    other_dept = Department(name="Экономика")
    db.add(other_dept)
    db.flush()

    other_group = StudyGroup(code="ЭК101", course=1, department_id=other_dept.id)
    db.add(other_group)

    curator_role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one()
    other_curator = User(
        username="other_dept_curator", full_name="Куратор Другого Отделения",
        role_id=curator_role.id, department_id=other_dept.id, password_hash=hash_password("x"),
    )
    db.add(other_curator)
    db.commit()
    db.refresh(other_group)
    db.refresh(other_curator)
    return {"department": other_dept, "group": other_group, "curator": other_curator}


def test_dept_head_groups_list_excludes_other_department(client, dept_head_headers, other_department_setup):
    r = client.get("/admin/groups", headers=dept_head_headers)
    assert r.status_code == 200
    codes = {g["code"] for g in r.json()}
    assert "ЭК101" not in codes
    assert "ИИ112" in codes  # своё отделение видно


def test_dept_head_cannot_override_scope_via_query_param(client, dept_head_headers, other_department_setup):
    other_dept_id = other_department_setup["department"].id
    r = client.get(f"/admin/groups?department_id={other_dept_id}", headers=dept_head_headers)
    assert r.status_code == 200
    codes = {g["code"] for g in r.json()}
    assert "ЭК101" not in codes  # параметр не помог обойти скоуп


def test_admin_groups_list_sees_all_departments(client, admin_headers, other_department_setup):
    r = client.get("/admin/groups", headers=admin_headers)
    codes = {g["code"] for g in r.json()}
    assert "ЭК101" in codes
    assert "ИИ112" in codes


def test_dept_head_users_list_excludes_other_department(client, dept_head_headers, other_department_setup):
    r = client.get("/admin/users", headers=dept_head_headers)
    usernames = {u["username"] for u in r.json()}
    assert "other_dept_curator" not in usernames


def test_dept_head_students_list_excludes_other_department_group(client, dept_head_headers, other_department_setup, db):
    from app.models import Student

    other_group = other_department_setup["group"]
    db.add(Student(last_name="Чужой", first_name="Студент", study_group_id=other_group.id, enrolled_at=datetime.date(2026, 9, 1)))
    db.commit()

    r = client.get(f"/admin/students?study_group_id={other_group.id}", headers=dept_head_headers)
    assert r.status_code == 200
    assert r.json() == []  # чужая группа — пустой список, а не чужие студенты


def test_dept_head_can_assign_curator_within_own_department(client, dept_head_headers, imported, db):
    vacant = db.query(StudyGroup).filter(StudyGroup.code == "ИИ132").one()  # вакансия из исходных данных
    role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one()
    own_curator = db.query(User).filter(User.role_id == role.id).first()

    r = client.post(
        "/admin/curator-assignments", headers=dept_head_headers,
        json={
            "study_group_id": vacant.id, "user_id": own_curator.id,
            "role_type": "curator", "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 201


def test_dept_head_cannot_assign_curator_to_other_department_group(client, dept_head_headers, other_department_setup):
    other_group = other_department_setup["group"]
    other_curator = other_department_setup["curator"]

    r = client.post(
        "/admin/curator-assignments", headers=dept_head_headers,
        json={
            "study_group_id": other_group.id, "user_id": other_curator.id,
            "role_type": "curator", "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 403


def test_dept_head_cannot_assign_curator_from_other_department(client, dept_head_headers, other_department_setup, db):
    ii132 = db.query(StudyGroup).filter(StudyGroup.code == "ИИ132").one()
    other_curator = other_department_setup["curator"]

    r = client.post(
        "/admin/curator-assignments", headers=dept_head_headers,
        json={
            "study_group_id": ii132.id, "user_id": other_curator.id,
            "role_type": "curator", "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 403


def test_edu_department_can_assign_across_departments(client, edu_department_headers, other_department_setup):
    other_group = other_department_setup["group"]
    other_curator = other_department_setup["curator"]

    r = client.post(
        "/admin/curator-assignments", headers=edu_department_headers,
        json={
            "study_group_id": other_group.id, "user_id": other_curator.id,
            "role_type": "curator", "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 201
