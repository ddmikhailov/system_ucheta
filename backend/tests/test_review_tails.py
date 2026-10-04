"""Хвосты повторного ревью (futures.md, этап 0): права воспитательного отдела
на структуру, смена отделения через роль, X-Forwarded-For, выходные."""
import datetime
from types import SimpleNamespace

from app.core.rate_limit import client_ip
from app.models import Department, Role, RoleCode, StudyGroup, User
from app.services import calendar_service


def _request(forwarded: str | None, host: str = "10.0.0.1"):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_ignores_spoofed_leading_entries():
    # клиент подсунул свой "1.2.3.4", прокси дописал реальный адрес справа
    assert client_ip(_request("1.2.3.4, 203.0.113.7")) == "203.0.113.7"


def test_client_ip_falls_back_to_transport_address():
    assert client_ip(_request(None)) == "10.0.0.1"


def test_edu_department_cannot_edit_or_delete_groups_and_students(client, edu_department_headers, curator_group, db):
    r = client.patch(f"/admin/groups/{curator_group.id}", headers=edu_department_headers, json={"name": "Х"})
    assert r.status_code == 403
    r = client.delete(f"/admin/groups/{curator_group.id}", headers=edu_department_headers)
    assert r.status_code == 403
    from app.models import Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    r = client.patch(f"/admin/students/{student.id}", headers=edu_department_headers, json={"full_name": "Х"})
    assert r.status_code == 403
    r = client.delete(f"/admin/students/{student.id}", headers=edu_department_headers)
    assert r.status_code == 403


def test_dept_head_cannot_move_curator_to_other_department_via_role_change(
    client, dept_head_headers, dept_head_user, curator_user, db
):
    other = Department(name="Другое отделение")
    db.add(other)
    db.commit()
    curator_user.department_id = dept_head_user.department_id
    db.commit()
    r = client.patch(
        f"/admin/users/{curator_user.id}",
        headers=dept_head_headers,
        json={"role": "deputy_curator", "department_id": other.id},
    )
    assert r.status_code == 200
    db.refresh(curator_user)
    assert curator_user.department_id == dept_head_user.department_id


def test_saturday_is_study_day_only_for_first_course(test_engine, db):
    saturday = datetime.date(2026, 9, 26)
    assert calendar_service.is_study_day(db, saturday, course=1) is True
    assert calendar_service.is_study_day(db, saturday, course=2) is False
    assert calendar_service.is_study_day(db, saturday) is False


def test_sunday_is_never_default_study_day(test_engine, db):
    sunday = datetime.date(2026, 9, 27)
    assert calendar_service.is_study_day(db, sunday, course=1) is False


def test_cannot_submit_attendance_on_weekend(client, curator_headers, curator_group, today):
    sunday = today - datetime.timedelta(days=(today.weekday() + 1) % 7 or 7)
    assert sunday.weekday() == 6
    r = client.post(f"/curator/groups/{curator_group.id}/day/mark-all-present?date={sunday}", headers=curator_headers)
    assert r.status_code in (400, 403, 409)


def _dept_head_world(db, dept_head_user):
    """Своё отделение (из фикстуры) + чужое отделение с группой."""
    other = Department(name="Чужое отделение")
    db.add(other)
    db.flush()
    foreign = StudyGroup(code="FOREIGN-1", course=1, department_id=other.id)
    db.add(foreign)
    db.commit()
    return other, foreign


def test_dept_head_has_full_edit_access_within_own_department(client, dept_head_headers, dept_head_user, db, imported, today):
    other, foreign = _dept_head_world(db, dept_head_user)
    own_id = dept_head_user.department_id

    r = client.post("/admin/groups", headers=dept_head_headers,
                    json={"code": "OWN-NEW", "course": 1, "department_id": own_id, "study_form": None})
    assert r.status_code == 201, r.text
    group_id = r.json()["id"]
    assert client.post("/admin/groups", headers=dept_head_headers,
                       json={"code": "FOR-NEW", "course": 1, "department_id": other.id}).status_code == 403

    r = client.post("/admin/students", headers=dept_head_headers,
                    json={"last_name": "Новый", "first_name": "С", "study_group_id": group_id, "enrolled_at": str(today)})
    assert r.status_code == 201, r.text
    assert client.post("/admin/students", headers=dept_head_headers,
                       json={"last_name": "Чужой", "first_name": "С", "study_group_id": foreign.id,
                             "enrolled_at": str(today)}).status_code == 403

    r = client.post("/admin/users", headers=dept_head_headers,
                    json={"username": "new_curator", "full_name": "Куратор", "role": "curator", "department_id": other.id})
    assert r.status_code == 201 and r.json()["department_id"] == own_id
    assert client.post("/admin/users", headers=dept_head_headers,
                       json={"username": "new_admin", "full_name": "А", "role": "admin"}).status_code == 403

    # Отделения и общие справочники по-прежнему не его.
    assert client.post("/admin/departments", headers=dept_head_headers, json={"name": "Н"}).status_code == 403


def test_dept_head_group_calendar_override_only_for_own_groups(client, dept_head_headers, dept_head_user, db, imported, today):
    other, foreign = _dept_head_world(db, dept_head_user)
    own = db.query(StudyGroup).filter(StudyGroup.department_id == dept_head_user.department_id).first()
    body = {"date": str(today), "day_type": "vacation"}
    assert client.put("/admin/calendar/group-overrides", headers=dept_head_headers,
                      json={**body, "study_group_id": own.id}).status_code == 200
    assert client.put("/admin/calendar/group-overrides", headers=dept_head_headers,
                      json={**body, "study_group_id": foreign.id}).status_code == 403
    assert client.get(f"/admin/calendar/group-overrides?study_group_id={foreign.id}&date_from={today}&date_to={today}",
                      headers=dept_head_headers).status_code == 403
    assert client.delete(f"/admin/calendar/group-overrides?study_group_id={own.id}&date={today}",
                         headers=dept_head_headers).status_code == 200
    # общий календарь колледжа — нет
    assert client.put("/admin/calendar", headers=dept_head_headers,
                      json={"date": str(today), "day_type": "holiday"}).status_code == 403
