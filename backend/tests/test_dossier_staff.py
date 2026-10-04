"""Соц. педагог и психолог: все группы и досье всех студентов колледжа, только
чтение посещаемости, никакого управления (futures.md, этап 1)."""
import pytest

from app.core.security import hash_password
from app.models import Department, Role, RoleCode, Student, StudyGroup, User
from tests.conftest import _login

PASSWORD = "StaffTest123!"


@pytest.fixture(params=["social_pedagogue", "psychologist"])
def staff_headers(request, client, db, seeded):
    role = db.query(Role).filter(Role.code == request.param).one()
    db.add(User(username=f"staff_{request.param}", full_name="Специалист", role_id=role.id,
                password_hash=hash_password(PASSWORD)))
    db.commit()
    return _login(client, f"staff_{request.param}", PASSWORD)


def test_staff_sees_dossier_of_any_student(client, staff_headers, imported, db):
    for student in db.query(Student).limit(3).all():
        r = client.get(f"/students/{student.id}/dossier", headers=staff_headers)
        assert r.status_code == 200
        assert client.get(f"/students/{student.id}", headers=staff_headers).status_code == 200


def test_staff_edits_dossier_including_special_fields(client, staff_headers, imported, db):
    student = db.query(Student).first()
    r = client.put(
        f"/students/{student.id}/dossier/profile", headers=staff_headers,
        json={"phone": "123", "special": {"has_ovz": True, "health_note": "заметка психолога"}},
    )
    assert r.status_code == 200 and r.json()["special"]["has_ovz"] is True
    assert client.post(f"/students/{student.id}/dossier/notes", headers=staff_headers,
                       json={"kind": "conversation", "text": "Беседа"}).status_code == 201


def test_staff_sees_all_groups_and_dashboards(client, staff_headers, imported, db, today):
    groups = client.get("/admin/groups", headers=staff_headers)
    assert groups.status_code == 200 and len(groups.json()) == db.query(StudyGroup).count()
    group = db.query(StudyGroup).first()
    assert client.get(f"/curator/groups/{group.id}/day?date={today}", headers=staff_headers).status_code == 200
    assert client.get(f"/dashboards/day?date={today}", headers=staff_headers).status_code == 200


def test_staff_search_students(client, staff_headers, imported, db):
    student = db.query(Student).first()
    r = client.get("/students", params={"q": student.last_name}, headers=staff_headers)
    assert r.status_code == 200 and student.id in [row["id"] for row in r.json()]
    r = client.get("/students", params={"group_id": student.study_group_id}, headers=staff_headers)
    assert all(row["group_code"] == student.study_group.code for row in r.json())


def test_curator_cannot_search_students(client, curator_headers):
    assert client.get("/students", headers=curator_headers).status_code == 403


def test_staff_cannot_write_attendance_or_manage(client, staff_headers, imported, db, today):
    group = db.query(StudyGroup).first()
    student = db.query(Student).filter(Student.study_group_id == group.id).first()
    assert client.post(
        f"/curator/groups/{group.id}/day/mark-all-present?date={today}", headers=staff_headers
    ).status_code == 403
    assert client.get("/admin/users", headers=staff_headers).status_code == 403
    assert client.patch(f"/admin/students/{student.id}", headers=staff_headers, json={"first_name": "Х"}).status_code == 403
    assert client.delete(f"/admin/groups/{group.id}", headers=staff_headers).status_code == 403
    assert client.put("/admin/calendar", headers=staff_headers, json={}).status_code in (403, 422)
    assert client.get(f"/students/{student.id}/dossier/access-log", headers=staff_headers).status_code == 403
    assert client.get(f"/dashboards/curator-discipline?date_from={today}&date_to={today}",
                      headers=staff_headers).status_code == 403


def test_staff_belongs_to_a_department(client, admin_headers, db):
    dept = db.query(Department).first()
    payload = {"username": "psy1", "full_name": "Психолог П.", "role": "psychologist"}
    assert client.post("/admin/users", headers=admin_headers, json=payload).status_code == 400
    r = client.post("/admin/users", headers=admin_headers, json={**payload, "department_id": dept.id})
    assert r.status_code == 201 and r.json()["department_id"] == dept.id


def test_dept_head_assigns_own_department_staff_as_curator(client, dept_head_headers, dept_head_user, db, imported, today):
    role = db.query(Role).filter(Role.code == "social_pedagogue").one()
    mine = User(username="sp_mine", full_name="Соц. педагог", role_id=role.id,
                department_id=dept_head_user.department_id, password_hash=hash_password(PASSWORD))
    other_dept = Department(name="Чужое отделение")
    db.add_all([mine, other_dept])
    db.flush()
    foreign = User(username="sp_foreign", full_name="Чужой", role_id=role.id,
                   department_id=other_dept.id, password_hash=hash_password(PASSWORD))
    db.add(foreign)
    db.commit()
    group = db.query(StudyGroup).filter(StudyGroup.department_id == dept_head_user.department_id).first()
    body = {"study_group_id": group.id, "role_type": "deputy", "start_date": str(today)}
    assert client.post("/admin/curator-assignments", headers=dept_head_headers,
                       json={**body, "user_id": mine.id}).status_code == 201
    assert client.post("/admin/curator-assignments", headers=dept_head_headers,
                       json={**body, "user_id": foreign.id}).status_code == 403


def test_staff_can_also_be_a_curator_of_own_groups(client, staff_headers, imported, db, admin_headers, today):
    """Куратором человек становится назначением на группу, а не ролью: психолог/соц.
    педагог ведёт свои группы (пишет посещаемость), а в чужих остаётся наблюдателем."""
    staff = db.query(User).filter(User.username.like("staff_%")).one()
    own, other = db.query(StudyGroup).order_by(StudyGroup.id).limit(2).all()
    r = client.post(
        "/admin/curator-assignments", headers=admin_headers,
        json={"study_group_id": own.id, "user_id": staff.id, "role_type": "curator", "start_date": str(today)},
    )
    assert r.status_code == 201

    me = client.get("/auth/me", headers=staff_headers).json()
    assert [g["id"] for g in me["groups"]] == [own.id]
    assert client.post(
        f"/curator/groups/{own.id}/day/mark-all-present?date={today}", headers=staff_headers
    ).status_code == 200
    assert client.post(
        f"/curator/groups/{other.id}/day/mark-all-present?date={today}", headers=staff_headers
    ).status_code == 403
    assert client.get(f"/curator/groups/{other.id}/day?date={today}", headers=staff_headers).status_code == 200


def test_staff_can_download_group_pdf_but_curator_cannot_for_foreign_group(client, staff_headers, curator_headers, curator_group, imported, db, today):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    url = f"/export/pdf/{other.id}?date_from={today}&date_to={today}"
    assert client.get(url, headers=staff_headers).status_code == 200
    assert client.get(url, headers=curator_headers).status_code == 403
