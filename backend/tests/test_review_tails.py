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
