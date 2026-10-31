"""Тексты родителям: опоздания, длительное отсутствие, собрание, итог семестра (роль × вид сообщения)."""
import datetime

import pytest

from app.models import AbsencePeriod, MarkCode, ParentMeeting, Student
from app.services import calendar_service


def _student(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).first()


def _url(student, kind):
    return f"/students/{student.id}/parent-message?kind={kind}"


def _mark(client, headers, group, student, code, day):
    r = client.post(f"/curator/groups/{group.id}/day/submit?date={day}", headers=headers, json={
        "exceptions": [{"student_id": student.id, "mark_code": code, "comment": None, "basis_reference": None}]})
    assert r.status_code == 200, r.text


def test_unknown_kind_is_rejected(client, curator_headers, curator_group, imported, db):
    s = _student(db, curator_group)
    assert client.get(_url(s, "spam"), headers=curator_headers).status_code == 400


def test_absences_kind_reuses_absence_message(client, curator_headers, curator_group, imported, db):
    s = _student(db, curator_group)
    body = client.get(_url(s, "absences"), headers=curator_headers).json()
    assert body["text"] == "" and "нет пропусков без уважительной причины" in body["empty_reason"]


def test_late_message_lists_only_late_marks(client, curator_headers, curator_user, curator_group, imported, db, today):
    s = _student(db, curator_group)
    study = calendar_service.study_days_between(
        db, today - datetime.timedelta(days=10), today, study_group_id=curator_group.id, course=curator_group.course)
    _mark(client, curator_headers, curator_group, s, "о", study[-1])
    _mark(client, curator_headers, curator_group, s, "н", study[-2])
    body = client.get(_url(s, "late"), headers=curator_headers).json()
    assert study[-1].strftime("%d.%m.%Y") in body["text"] and study[-2].strftime("%d.%m.%Y") not in body["text"]
    assert s.full_name in body["text"] and curator_user.full_name in body["text"]


def test_late_message_empty_without_lates(client, curator_headers, curator_group, imported, db):
    s = _student(db, curator_group)
    body = client.get(_url(s, "late"), headers=curator_headers).json()
    assert body["text"] == "" and "нет опозданий" in body["empty_reason"]


def test_long_absence_message_uses_recent_period(client, curator_headers, curator_group, imported, db, today, curator_user):
    s = _student(db, curator_group)
    assert client.get(_url(s, "long_absence"), headers=curator_headers).json()["text"] == ""
    code = db.query(MarkCode).filter_by(code="б").one()
    db.add(AbsencePeriod(student_id=s.id, mark_code_id=code.id, date_from=today - datetime.timedelta(days=3),
                         date_to=today + datetime.timedelta(days=4), basis_reference="Справка №7",
                         created_by_user_id=curator_user.id))
    db.commit()
    text = client.get(_url(s, "long_absence"), headers=curator_headers).json()["text"]
    assert "продолжается" in text and "Справка №7" in text and code.name in text


def test_meeting_message_needs_future_meeting(client, curator_headers, curator_group, imported, db, today, curator_user):
    s = _student(db, curator_group)
    assert client.get(_url(s, "meeting"), headers=curator_headers).json()["text"] == ""
    db.add(ParentMeeting(study_group_id=curator_group.id, school_year="2026-2027", number=1,
                         meeting_date=today + datetime.timedelta(days=5), agenda="Итоги месяца\nЗачёты",
                         meeting_format="remote", created_by_user_id=curator_user.id))
    db.commit()
    text = client.get(_url(s, "meeting"), headers=curator_headers).json()["text"]
    assert (today + datetime.timedelta(days=5)).strftime("%d.%m.%Y") in text
    assert "дистанционно" in text and "• Итоги месяца" in text and "• Зачёты" in text


def test_semester_message_shows_attendance_only(client, curator_headers, curator_group, imported, db, today):
    s = _student(db, curator_group)
    study = calendar_service.study_days_between(
        db, today - datetime.timedelta(days=10), today, study_group_id=curator_group.id, course=curator_group.course)
    _mark(client, curator_headers, curator_group, s, "н", study[-1])
    body = client.get(_url(s, "semester"), headers=curator_headers).json()
    if body["text"]:
        assert "посещаемость" in body["text"] and "без уважительной причины — 1" in body["text"]
        assert "оцен" not in body["text"].lower()
    else:  # сданных дней в семестре нет (например, каникулы)
        assert "нет сданных дней" in body["empty_reason"]


@pytest.mark.parametrize("kind", ["absences", "late", "long_absence", "meeting", "semester"])
def test_parent_message_follows_student_access(client, curator_group, db_second_curator, curator_headers, admin_headers,
                                               imported, db, kind):
    from tests.conftest import _login
    s = _student(db, curator_group)
    other = _login(client, db_second_curator.username, "SecondCura#58x!")
    assert client.get(_url(s, kind), headers=other).status_code == 403
    assert client.get(_url(s, kind), headers=admin_headers).status_code == 200
    assert client.get(_url(s, kind)).status_code == 401
    assert client.get(f"/students/999999/parent-message?kind={kind}", headers=admin_headers).status_code == 404
