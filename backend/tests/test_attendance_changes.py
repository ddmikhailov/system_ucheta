"""Правка прошлого сданного дня куратором — через проверку зав. отделением (интерфейс 3.2)."""
import datetime

import pytest

from app.core.time import today_local
from app.models import AttendanceMark, Department, DaySubmission, InAppNotification, Student
from app.services import calendar_service


def _past_study_day(db, group) -> datetime.date:
    today = today_local()
    days = calendar_service.study_days_by_group(db, today - datetime.timedelta(days=21), today - datetime.timedelta(days=1), [group])[group.id]
    return days[-1]


def _students(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).all()


@pytest.fixture()
def submitted_past(client, curator_headers, curator_group, db):
    """Прошлый учебный день, сданный куратором (первая сдача задним числом — без проверки)."""
    day = _past_study_day(db, curator_group)
    first = _students(db, curator_group)[0]
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date={day}", headers=curator_headers,
        json={"exceptions": [{"student_id": first.id, "mark_code": "н"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["edit_requires_review"] is True
    return day


def _change(client, headers, group, day, exceptions, reason="Пришла справка из поликлиники"):
    return client.post(
        f"/curator/groups/{group.id}/day/change-request?date={day}", headers=headers,
        json={"exceptions": exceptions, "reason": reason},
    )


def test_first_late_submission_is_direct_and_today_is_free(client, curator_headers, curator_group, db, today):
    day = _past_study_day(db, curator_group)
    r = client.get(f"/curator/groups/{curator_group.id}/day?date={day}", headers=curator_headers)
    assert r.json()["edit_requires_review"] is False  # прошлый, но не сданный — сдаётся сразу
    r = client.post(f"/curator/groups/{curator_group.id}/day/mark-all-present?date={today}", headers=curator_headers)
    assert r.status_code == 200
    again = client.post(f"/curator/groups/{curator_group.id}/day/mark-all-present?date={today}", headers=curator_headers)
    assert again.status_code == 200 and again.json()["edit_requires_review"] is False  # сегодня правит сам


def test_direct_edit_of_submitted_past_day_is_refused(client, curator_headers, curator_group, db, submitted_past):
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date={submitted_past}", headers=curator_headers,
        json={"exceptions": []},
    )
    assert r.status_code == 409 and "проверку" in r.json()["detail"]
    r = client.post(f"/curator/groups/{curator_group.id}/day/mark-all-present?date={submitted_past}&confirm=true", headers=curator_headers)
    assert r.status_code == 409


def test_request_then_approve_applies_marks_keeps_on_time(
    client, curator_headers, curator_user, curator_group, dept_head_headers, dept_head_user, db, submitted_past,
):
    first, second = _students(db, curator_group)[:2]
    before = db.query(DaySubmission).filter_by(study_group_id=curator_group.id, date=submitted_past).one()
    on_time_before = before.is_on_time

    r = _change(client, curator_headers, curator_group, submitted_past,
                [{"student_id": first.id, "mark_code": "б", "basis_reference": "Справка №12"},
                 {"student_id": second.id, "mark_code": "о"}])
    assert r.status_code == 200, r.text
    pending = r.json()["pending_change"]
    assert pending["status"] == "pending" and pending["reason"] == "Пришла справка из поликлиники"
    changes = {c["student_id"]: (c["from_code"], c["to_code"]) for c in pending["changes"]}
    assert changes == {first.id: ("н", "б"), second.id: (None, "о")}
    # до решения журнал не меняется
    db.expire_all()
    assert db.query(AttendanceMark).filter_by(student_id=first.id, date=submitted_past).one().mark_code.code == "н"
    # зав. отделением получил уведомление со ссылкой на день
    note = db.query(InAppNotification).filter_by(user_id=dept_head_user.id, kind="attendance_change").one()
    assert note.entity_id == f"{curator_group.id}:{submitted_past.isoformat()}"

    listed = client.get("/attendance-changes", headers=dept_head_headers).json()
    assert [x["id"] for x in listed] == [pending["id"]]
    assert client.get("/attendance-changes", headers=curator_headers).status_code == 403

    r = client.post(f"/attendance-changes/{pending['id']}/approve", headers=dept_head_headers, json={})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    db.expire_all()
    marks = {m.student_id: m for m in db.query(AttendanceMark).filter_by(date=submitted_past).all()}
    assert marks[first.id].mark_code.code == "б" and marks[first.id].basis_reference == "Справка №12"
    assert marks[second.id].mark_code.code == "о"
    assert marks[first.id].updated_by_user_id == curator_user.id  # от имени куратора
    after = db.query(DaySubmission).filter_by(study_group_id=curator_group.id, date=submitted_past).one()
    assert after.is_on_time == on_time_before
    assert db.query(InAppNotification).filter_by(user_id=curator_user.id, kind="attendance_change_approved").count() == 1

    day = client.get(f"/curator/groups/{curator_group.id}/day?date={submitted_past}", headers=curator_headers).json()
    assert day["pending_change"] is None and day["last_change"]["status"] == "approved"
    assert client.get("/attendance-changes", headers=dept_head_headers).json() == []


def test_reject_needs_comment_and_keeps_journal(client, curator_headers, curator_user, curator_group, dept_head_headers, db, submitted_past):
    first = _students(db, curator_group)[0]
    req = _change(client, curator_headers, curator_group, submitted_past, []).json()["pending_change"]
    assert client.post(f"/attendance-changes/{req['id']}/reject", headers=dept_head_headers, json={}).status_code == 400
    r = client.post(f"/attendance-changes/{req['id']}/reject", headers=dept_head_headers, json={"comment": "Нет документа"})
    assert r.status_code == 200 and r.json()["review_comment"] == "Нет документа"
    db.expire_all()
    assert db.query(AttendanceMark).filter_by(student_id=first.id, date=submitted_past).one().mark_code.code == "н"
    again = client.post(f"/attendance-changes/{req['id']}/approve", headers=dept_head_headers, json={})
    assert again.status_code == 409  # уже решён


def test_new_request_replaces_pending_and_author_can_cancel(client, curator_headers, curator_group, dept_head_headers, db, submitted_past):
    a = _change(client, curator_headers, curator_group, submitted_past, []).json()["pending_change"]
    b = _change(client, curator_headers, curator_group, submitted_past, [], reason="Уточнение").json()["pending_change"]
    assert a["id"] != b["id"]
    assert [x["id"] for x in client.get("/attendance-changes", headers=dept_head_headers).json()] == [b["id"]]
    assert client.post(f"/attendance-changes/{b['id']}/cancel", headers=dept_head_headers).status_code == 403
    assert client.post(f"/attendance-changes/{b['id']}/cancel", headers=curator_headers).json()["status"] == "cancelled"
    assert client.get("/attendance-changes", headers=dept_head_headers).json() == []


def test_request_validation(client, curator_headers, curator_group, db, submitted_past, today):
    assert _change(client, curator_headers, curator_group, submitted_past, [], reason="ok").status_code == 422  # причина короче 3
    assert _change(client, curator_headers, curator_group, submitted_past,
                   [{"student_id": 999999, "mark_code": "н"}]).status_code == 400
    # сегодняшний день — без проверки, запрос не нужен
    client.post(f"/curator/groups/{curator_group.id}/day/mark-all-present?date={today}", headers=curator_headers)
    assert _change(client, curator_headers, curator_group, today, []).status_code == 409


def test_admin_edits_directly_and_other_department_cannot_review(
    client, admin_headers, curator_headers, curator_group, dept_head_user, dept_head_headers, db, submitted_past,
):
    r = client.post(f"/curator/groups/{curator_group.id}/day/submit?date={submitted_past}", headers=admin_headers, json={"exceptions": []})
    assert r.status_code == 200 and r.json()["edit_requires_review"] is False  # администрация правит сразу

    req = _change(client, curator_headers, curator_group, submitted_past, []).json()["pending_change"]
    other = Department(name="Другое отделение (синт.)")
    db.add(other)
    db.flush()
    dept_head_user.department_id = other.id
    db.commit()
    assert client.post(f"/attendance-changes/{req['id']}/approve", headers=dept_head_headers, json={}).status_code == 403
    assert client.get("/attendance-changes", headers=dept_head_headers).json() == []
    assert client.post(f"/attendance-changes/{req['id']}/approve", headers=admin_headers, json={}).status_code == 200


def test_roster_shows_who_submitted(client, curator_headers, curator_user, curator_group, submitted_past):
    day = client.get(f"/curator/groups/{curator_group.id}/day?date={submitted_past}", headers=curator_headers).json()
    assert day["submitted_by_name"] == curator_user.full_name


def test_menu_counter_for_reviewer(client, curator_headers, curator_group, dept_head_headers, admin_headers, db, submitted_past):
    assert client.get("/my-day/counters", headers=dept_head_headers).json()["journal_changes"] == 0
    _change(client, curator_headers, curator_group, submitted_past, [])
    assert client.get("/my-day/counters", headers=dept_head_headers).json()["journal_changes"] == 1
    assert client.get("/my-day/counters", headers=admin_headers).json()["journal_changes"] == 1
    assert client.get("/my-day/counters", headers=curator_headers).json()["journal_changes"] == 0
