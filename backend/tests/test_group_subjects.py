"""Дисциплины и преподаватели группы (п. 5.1.5 положения): роль × действие, проверки ввода."""
import pytest

from app.core.security import hash_password
from app.models import CuratorAssignment, Department, GroupSubject, Role, RoleCode, StudyGroup, User
from tests.conftest import _login

PASSWORD = "SubjectsTest#58x!"
BODY = {"code": "МДК.01.01", "name": "Компьютерные сети", "teacher_name": "Иванова И. И.", "teacher_phone": "+7 900 000-00-00"}


def url(group_id, subject_id=None):
    return f"/groups/{group_id}/subjects" + (f"/{subject_id}" if subject_id else "")


def staff_headers(client, db, role_code, department_id=None):
    role = db.query(Role).filter(Role.code == role_code).one()
    db.add(User(username=f"s_{role_code}", full_name="Сотрудник", role_id=role.id, department_id=department_id,
                password_hash=hash_password(PASSWORD)))
    db.commit()
    return _login(client, f"s_{role_code}", PASSWORD)


@pytest.fixture()
def foreign_group(db, curator_user, curator_group):
    """Группа, которую куратор не ведёт."""
    led = {a.study_group_id for a in db.query(CuratorAssignment).filter(CuratorAssignment.user_id == curator_user.id)}
    group = db.query(StudyGroup).filter(StudyGroup.id.notin_(led)).first()
    assert group is not None
    return group


@pytest.fixture()
def other_department_group(db, imported):
    dept = Department(name="Экономика")
    db.add(dept)
    db.flush()
    group = StudyGroup(code="ЭК101", course=1, department_id=dept.id)
    db.add(group)
    db.commit()
    return group


def test_curator_crud_in_own_group(client, curator_headers, curator_group):
    created = client.post(url(curator_group.id), json=BODY, headers=curator_headers)
    assert created.status_code == 201
    sid = created.json()["id"]
    listing = client.get(url(curator_group.id), headers=curator_headers).json()
    assert listing["can_edit"] is True and [s["name"] for s in listing["subjects"]] == ["Компьютерные сети"]
    upd = client.put(url(curator_group.id, sid), json={**BODY, "teacher_phone": "  +7 911  "}, headers=curator_headers)
    assert upd.status_code == 200 and upd.json()["teacher_phone"] == "+7 911"
    assert client.delete(url(curator_group.id, sid), headers=curator_headers).status_code == 204
    assert client.get(url(curator_group.id), headers=curator_headers).json()["subjects"] == []


def test_validation_and_duplicates(client, curator_headers, curator_group):
    assert client.post(url(curator_group.id), json={"name": "   "}, headers=curator_headers).status_code == 422
    assert client.post(url(curator_group.id), json=BODY, headers=curator_headers).status_code == 201
    same_name = client.post(url(curator_group.id), json={"name": "компьютерные СЕТИ"}, headers=curator_headers)
    assert same_name.status_code == 409
    same_code = client.post(url(curator_group.id), json={"code": "мдк.01.01", "name": "Другая"}, headers=curator_headers)
    assert same_code.status_code == 409
    # без кода можно вести сколько угодно разных дисциплин
    assert client.post(url(curator_group.id), json={"name": "История"}, headers=curator_headers).status_code == 201
    assert client.post(url(curator_group.id), json={"name": "Физика"}, headers=curator_headers).status_code == 201


def test_curator_cannot_touch_foreign_group(client, curator_headers, foreign_group, admin_headers):
    sid = client.post(url(foreign_group.id), json=BODY, headers=admin_headers).json()["id"]
    assert client.get(url(foreign_group.id), headers=curator_headers).status_code == 403
    assert client.post(url(foreign_group.id), json=BODY, headers=curator_headers).status_code == 403
    assert client.put(url(foreign_group.id, sid), json=BODY, headers=curator_headers).status_code == 403
    assert client.delete(url(foreign_group.id, sid), headers=curator_headers).status_code == 403


def test_subject_must_belong_to_group(client, curator_headers, curator_group, foreign_group, admin_headers):
    sid = client.post(url(foreign_group.id), json=BODY, headers=admin_headers).json()["id"]
    assert client.put(url(curator_group.id, sid), json=BODY, headers=curator_headers).status_code == 404
    assert client.delete(url(curator_group.id, sid), headers=curator_headers).status_code == 404


def test_unknown_group_is_404(client, admin_headers):
    assert client.get(url(999999), headers=admin_headers).status_code == 404


def test_admin_edits_any_group(client, admin_headers, foreign_group):
    assert client.post(url(foreign_group.id), json=BODY, headers=admin_headers).status_code == 201
    assert client.get(url(foreign_group.id), headers=admin_headers).json()["can_edit"] is True


@pytest.mark.parametrize("role", ["social_pedagogue", "psychologist"])
def test_staff_reads_any_group_but_edits_only_led(client, db, role, foreign_group, admin_headers):
    headers = staff_headers(client, db, role)
    client.post(url(foreign_group.id), json=BODY, headers=admin_headers)
    listing = client.get(url(foreign_group.id), headers=headers).json()
    assert listing["can_edit"] is False and len(listing["subjects"]) == 1
    assert client.post(url(foreign_group.id), json={"name": "История"}, headers=headers).status_code == 403


@pytest.mark.parametrize("role", ["dept_head", "tutor", "edu_department"])
def test_department_roles_work_in_own_department_only(client, db, role, foreign_group, other_department_group, admin_headers):
    headers = staff_headers(client, db, role, foreign_group.department_id)
    assert client.post(url(foreign_group.id), json=BODY, headers=headers).status_code == 201
    assert client.get(url(foreign_group.id), headers=headers).json()["can_edit"] is True
    assert client.get(url(other_department_group.id), headers=headers).status_code == 403
    assert client.post(url(other_department_group.id), json=BODY, headers=headers).status_code == 403


def test_meal_manager_has_no_access(client, meal_manager_headers, curator_group):
    assert client.get(url(curator_group.id), headers=meal_manager_headers).status_code == 403


def test_requires_login(client, curator_group):
    assert client.get(url(curator_group.id)).status_code in (401, 403)


def test_group_deletion_removes_subjects(client, db, admin_headers, foreign_group):
    client.post(url(foreign_group.id), json=BODY, headers=admin_headers)
    gid = foreign_group.id
    r = client.delete(f"/admin/groups/{gid}", params={"force": True, "confirm_code": foreign_group.code}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert db.query(GroupSubject).filter(GroupSubject.study_group_id == gid).count() == 0
