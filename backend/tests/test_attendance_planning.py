"""Правка посещаемости вперёд: на ещё не наступившие дни можно заранее внести отметки (заявление, ИУП),
не сдавая день и без ограничения по датам."""
import datetime

import pytest

from app.models import AttendanceMark, DaySubmission, Student
from app.services import attendance_service


@pytest.fixture()
def future_day(today):
    return today + datetime.timedelta(days=14)  # тот же будний день через две недели


def _student(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).first()


def test_plan_saves_marks_without_submitting_the_day(client, curator_headers, curator_group, db, future_day):
    s = _student(db, curator_group)
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/plan?date={future_day}", headers=curator_headers,
        json={"exceptions": [{"student_id": s.id, "mark_code": "б"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_submitted"] is False
    assert next(e for e in body["entries"] if e["student_id"] == s.id)["mark_code"] == "б"
    assert db.query(DaySubmission).filter(DaySubmission.study_group_id == curator_group.id, DaySubmission.date == future_day).count() == 0


def test_plan_has_no_date_limit(client, curator_headers, curator_group, db, today):
    s = _student(db, curator_group)
    far = today + datetime.timedelta(days=400)
    while far.weekday() >= 5:
        far += datetime.timedelta(days=1)
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/plan?date={far}", headers=curator_headers,
        json={"exceptions": [{"student_id": s.id, "mark_code": "б"}]},
    )
    assert r.status_code == 200, r.text


def test_plan_can_be_replaced_and_cleared(client, curator_headers, curator_group, db, future_day):
    s = _student(db, curator_group)
    url = f"/curator/groups/{curator_group.id}/day/plan?date={future_day}"
    client.post(url, headers=curator_headers, json={"exceptions": [{"student_id": s.id, "mark_code": "б"}]})
    client.post(url, headers=curator_headers, json={"exceptions": []})
    assert db.query(AttendanceMark).filter(AttendanceMark.student_id == s.id, AttendanceMark.date == future_day).count() == 0


def test_plan_rejects_today_and_past(client, curator_headers, curator_group, today):
    for day in (today, today - datetime.timedelta(days=1)):
        r = client.post(f"/curator/groups/{curator_group.id}/day/plan?date={day}", headers=curator_headers, json={"exceptions": []})
        assert r.status_code == 400


def test_submit_of_future_day_is_still_refused(client, curator_headers, curator_group, future_day):
    r = client.post(f"/curator/groups/{curator_group.id}/day/submit?date={future_day}", headers=curator_headers, json={"exceptions": []})
    assert r.status_code == 403
    assert "Сохранить план" in r.json()["detail"]


def test_plan_on_non_study_day_is_refused(client, curator_headers, curator_group, today):
    sunday = today + datetime.timedelta(days=(6 - today.weekday()) % 7 or 7)
    r = client.post(f"/curator/groups/{curator_group.id}/day/plan?date={sunday}", headers=curator_headers, json={"exceptions": []})
    assert r.status_code == 400


def test_planned_marks_are_in_the_journal_when_the_day_comes(db, curator_group, curator_user, future_day):
    s = _student(db, curator_group)
    attendance_service.submit_day(
        db, curator_group.id, future_day, [{"student_id": s.id, "mark_code": "б"}], curator_user,
        today=future_day - datetime.timedelta(days=10), plan_only=True,
    )
    roster = attendance_service.get_roster(db, curator_group.id, future_day)
    assert roster["is_submitted"] is False
    assert next(e for e in roster["entries"] if e["student_id"] == s.id)["mark_code"] == "б"


def test_no_yesterdays_draft_on_future_days(db, curator_group, curator_user, today, future_day):
    s = _student(db, curator_group)
    prev = attendance_service.calendar_service.previous_study_day(db, future_day, study_group_id=curator_group.id)
    attendance_service.submit_day(db, curator_group.id, prev, [{"student_id": s.id, "mark_code": "н"}], curator_user, today=prev)
    roster = attendance_service.get_roster(db, curator_group.id, future_day)
    assert all(e["mark_code"] is None for e in roster["entries"])


def test_only_people_with_access_to_the_group_can_plan(client, db_second_curator, curator_group, future_day):
    from tests.conftest import _login

    headers = _login(client, db_second_curator.username, "SecondCurator123!")
    r = client.post(f"/curator/groups/{curator_group.id}/day/plan?date={future_day}", headers=headers, json={"exceptions": []})
    assert r.status_code == 403


def test_month_status_covers_future_days_and_counts_planned_marks(client, curator_headers, curator_group, db, future_day):
    s = _student(db, curator_group)
    client.post(f"/curator/groups/{curator_group.id}/day/plan?date={future_day}", headers=curator_headers,
                json={"exceptions": [{"student_id": s.id, "mark_code": "б"}]})
    r = client.get(f"/curator/groups/{curator_group.id}/month-status?year={future_day.year}&month={future_day.month}", headers=curator_headers)
    assert r.status_code == 200
    by_date = {d["date"]: d for d in r.json()}
    assert by_date[future_day.isoformat()]["marks_count"] == 1
    assert by_date[future_day.isoformat()]["is_submitted"] is False
