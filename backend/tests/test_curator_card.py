"""Карточка работы куратора (положение, п. 3.7): кто видит и что считается."""
import datetime

import pytest

from app.models import Department, StudyGroup, Student
from app.models.enums import StudentStatus
from app.services import attendance_service, curator_card_service

DAY1 = datetime.date(2026, 9, 21)


def _url(date_to=DAY1, date_from=DAY1):
    return f"/dashboards/curator-card?date_from={date_from}&date_to={date_to}"


def test_curator_cannot_open_card(client, curator_headers):
    assert client.get(_url(), headers=curator_headers).status_code == 403


@pytest.mark.parametrize("headers_fixture", ["admin_headers", "dept_head_headers", "edu_department_headers"])
def test_management_roles_open_card(request, client, imported, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)
    r = client.get(_url(), headers=headers)
    assert r.status_code == 200
    assert r.json()


def test_dept_head_sees_only_own_department(client, db, imported, dept_head_user, dept_head_headers):
    other = Department(name="Другое отделение")
    db.add(other)
    db.flush()
    db.add(StudyGroup(code="ЧУЖ-1", course=1, department_id=other.id, is_active=True))
    db.commit()
    rows = client.get(_url(), headers=dept_head_headers).json()
    assert rows and all(r["department_id"] == dept_head_user.department_id for r in rows)
    assert "ЧУЖ-1" not in {r["code"] for r in rows}
    # чужое отделение в параметре не открывает чужие группы
    rows = client.get(_url() + f"&department_id={other.id}", headers=dept_head_headers).json()
    assert all(r["department_id"] == dept_head_user.department_id for r in rows)


def test_card_counts_attendance_discipline_and_contingent(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    attendance_service.submit_day(
        db, curator_group.id, DAY1,
        [{"student_id": students[0].id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=DAY1,
    )
    leaver = students[1]
    leaver.status, leaver.left_at = StudentStatus.EXPELLED, DAY1
    students[2].status = StudentStatus.ACADEMIC_LEAVE
    db.commit()

    card = next(c for c in curator_card_service.curator_cards(db, DAY1, DAY1) if c["study_group_id"] == curator_group.id)
    assert card["on_time"] == 1 and card["missed"] == card["total_study_days"] - 1
    assert card["attendance_percent"] is not None and card["attendance_percent"] < 100
    assert card["absent_unexcused_percent"] > 0
    assert card["contingent"]["left"] == 1
    assert card["contingent"]["academic_leave"] == 1
    assert card["students_count"] == len(students) - 2
    assert card["responsible_name"]


def test_card_without_submitted_days_has_no_percent(imported, db, curator_group):
    card = next(c for c in curator_card_service.curator_cards(db, DAY1, DAY1) if c["study_group_id"] == curator_group.id)
    assert card["attendance_percent"] is None and card["risk_count"] == 0
