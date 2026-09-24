"""Регрессионные тесты на продуктовые баги из ревью 25.09.2026 (TODO.md,
раздел 3)."""
import datetime


def test_unsubmitted_day_shows_no_data_not_100_percent(client, admin_headers, curator_group, today):
    """Раньше несданный день молча считался за 100% присутствия."""
    r = client.get("/dashboards/day", headers=admin_headers, params={"date": today.isoformat()})
    assert r.status_code == 200
    row = next(x for x in r.json() if x["study_group_id"] == curator_group.id)
    assert row["is_submitted"] is False
    assert row["percent"] is None
    assert row["in_list"] is None


def test_submitted_day_shows_real_percent(client, admin_headers, curator_headers, curator_group, today):
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/mark-all-present",
        headers=curator_headers, params={"date": today.isoformat()},
    )
    assert r.status_code == 200

    r = client.get("/dashboards/day", headers=admin_headers, params={"date": today.isoformat()})
    row = next(x for x in r.json() if x["study_group_id"] == curator_group.id)
    assert row["is_submitted"] is True
    assert row["percent"] == 100.0


def test_student_returning_to_studying_clears_left_at(client, admin_headers, imported, db):
    from app.models import Student, StudentStatus

    student = db.query(Student).filter(Student.status == StudentStatus.STUDYING).first()
    r = client.patch(
        f"/admin/students/{student.id}/status", headers=admin_headers,
        json={"status": "academic_leave", "left_at": "2026-09-01"},
    )
    assert r.status_code == 200
    assert r.json()["left_at"] == "2026-09-01"

    r = client.patch(f"/admin/students/{student.id}/status", headers=admin_headers, json={"status": "studying"})
    assert r.status_code == 200
    assert r.json()["left_at"] is None


def test_cannot_submit_non_study_day(client, curator_headers, curator_group, db):
    from app.models import StudyGroup

    group = db.get(StudyGroup, curator_group.id)
    sunday = datetime.date(2026, 9, 27)
    assert sunday.weekday() == 6

    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit",
        headers=curator_headers, params={"date": sunday.isoformat()},
        json={"exceptions": []},
    )
    assert r.status_code == 403


def test_dept_head_cannot_submit_future_day(client, dept_head_headers, imported, db):
    from app.models import Role, StudyGroup, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    dept_head = db.query(User).filter(User.username == "zavotd").one()
    group = (
        db.query(StudyGroup)
        .filter(StudyGroup.department_id == dept_head.department_id, StudyGroup.is_active.is_(True))
        .first()
    )
    far_future = datetime.date.today() + datetime.timedelta(days=10)
    r = client.post(
        f"/curator/groups/{group.id}/day/submit",
        headers=dept_head_headers, params={"date": far_future.isoformat()},
        json={"exceptions": []},
    )
    assert r.status_code == 403


def test_submit_rejects_unknown_mark_code(client, curator_headers, curator_group, curator_user, db, today):
    from app.models import Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit",
        headers=curator_headers, params={"date": today.isoformat()},
        json={"exceptions": [{"student_id": student.id, "mark_code": "not-a-real-code"}]},
    )
    assert r.status_code == 400


def test_submit_rejects_student_outside_group(client, curator_headers, curator_group, db, today):
    from app.models import Student, StudyGroup

    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    outsider = db.query(Student).filter(Student.study_group_id == other_group.id).first()
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit",
        headers=curator_headers, params={"date": today.isoformat()},
        json={"exceptions": [{"student_id": outsider.id, "mark_code": "н"}]},
    )
    assert r.status_code == 400


def test_absence_period_rejects_reversed_dates(client, curator_headers, curator_group, db):
    from app.models import Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    r = client.post(
        "/curator/absence-periods", headers=curator_headers,
        json={
            "student_id": student.id, "mark_code": "б",
            "date_from": "2026-09-10", "date_to": "2026-09-01",
        },
    )
    assert r.status_code == 400


def test_absence_period_rejects_future_dates(client, curator_headers, curator_group, db):
    from app.models import Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    far_future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    r = client.post(
        "/curator/absence-periods", headers=curator_headers,
        json={"student_id": student.id, "mark_code": "б", "date_from": far_future, "date_to": far_future},
    )
    assert r.status_code == 400


def test_absence_period_rejects_non_excused_code(client, curator_headers, curator_group, db, today):
    from app.models import Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    r = client.post(
        "/curator/absence-periods", headers=curator_headers,
        json={
            "student_id": student.id, "mark_code": "н",
            "date_from": today.isoformat(), "date_to": today.isoformat(),
        },
    )
    assert r.status_code == 400


def test_calendar_exception_can_be_deleted(client, admin_headers):
    r = client.put("/admin/calendar", headers=admin_headers, json={"date": "2026-11-04", "day_type": "holiday"})
    assert r.status_code == 200

    r = client.delete("/admin/calendar/2026-11-04", headers=admin_headers)
    assert r.status_code == 200

    r = client.get("/admin/calendar", headers=admin_headers, params={"date_from": "2026-11-01", "date_to": "2026-11-30"})
    assert r.json() == []


def test_group_override_delete_endpoint_still_works_after_reordering(client, admin_headers, imported, db):
    """Регрессия на конфликт маршрутов: DELETE /calendar/{date} был
    зарегистрирован раньше DELETE /calendar/group-overrides и перехватывал
    его (см. коммит с этим тестом)."""
    from app.models import StudyGroup

    group = db.query(StudyGroup).first()
    r = client.put(
        "/admin/calendar/group-overrides", headers=admin_headers,
        json={"study_group_id": group.id, "date": "2026-10-05", "day_type": "remote"},
    )
    assert r.status_code == 200
    r = client.delete(
        f"/admin/calendar/group-overrides?study_group_id={group.id}&date=2026-10-05", headers=admin_headers,
    )
    assert r.status_code == 200


def test_duplicate_group_code_returns_409_not_500(client, admin_headers, imported, db):
    from app.models import Department

    dept = db.query(Department).first()
    r = client.post(
        "/admin/groups", headers=admin_headers,
        json={"code": "DUPTEST", "course": 1, "department_id": dept.id},
    )
    assert r.status_code == 201
    r = client.post(
        "/admin/groups", headers=admin_headers,
        json={"code": "DUPTEST", "course": 1, "department_id": dept.id},
    )
    assert r.status_code == 409


def test_invalid_month_returns_400_not_500(client, curator_headers, curator_group):
    r = client.get(
        f"/curator/groups/{curator_group.id}/month-status", headers=curator_headers,
        params={"year": 2026, "month": 13},
    )
    assert r.status_code == 400


def test_pdf_export_for_nonexistent_group_returns_404(client, admin_headers):
    r = client.get(
        "/export/pdf/999999", headers=admin_headers,
        params={"date_from": "2026-09-01", "date_to": "2026-09-10"},
    )
    assert r.status_code == 404


def test_invalid_role_type_returns_422_not_500(client, admin_headers, imported, db):
    from app.models import Role, StudyGroup, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()
    group = db.query(StudyGroup).first()
    r = client.post(
        "/admin/curator-assignments", headers=admin_headers,
        json={
            "study_group_id": group.id, "user_id": curator.id, "role_type": "not-a-role",
            "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 422


def test_curator_discipline_and_day_overview_include_responsible_name(client, admin_headers, curator_group, curator_user, today):
    r = client.get(
        "/dashboards/curator-discipline", headers=admin_headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert r.status_code == 200
    row = next(x for x in r.json() if x["study_group_id"] == curator_group.id)
    assert row["responsible_name"] == curator_user.full_name
