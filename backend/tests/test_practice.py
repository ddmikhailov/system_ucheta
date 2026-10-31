"""Практика группы (п. 3.1.17 положения о кураторе): отметка «р» всем студентам, права, сводка. Данные выдуманные."""
import datetime

from app.models import AbsencePeriod, AttendanceMark, GroupPractice, Student
from app.services import attendance_service, calendar_service, group_membership_service

from app.core.time import today_local
from tests.conftest import _login


def _body(today, **extra):
    body = {"kind": "production", "date_from": (today - datetime.timedelta(days=7)).isoformat(),
            "date_to": (today + datetime.timedelta(days=7)).isoformat(), "base": "ООО «Ромашка»",
            "college_supervisor": "Иванова И. И.", "base_supervisor": "Петров П. П.", "phone": "+7 000 000-00-00"}
    return {**body, **extra}


def _study_days(db, group, today):
    return calendar_service.study_days_between(
        db, today - datetime.timedelta(days=7), today + datetime.timedelta(days=7), study_group_id=group.id,
    )


def _create(client, headers, group, today, **extra):
    r = client.post(f"/practice/groups/{group.id}", headers=headers, json=_body(today, **extra))
    assert r.status_code == 201, r.text
    return r.json()


def _students(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).all()


def test_practice_marks_every_student_on_study_days(client, curator_headers, curator_group, db, today):
    practice = _create(client, curator_headers, curator_group, today)
    assert practice["kind_name"] == "Производственная" and practice["state"] == "active"
    days = _study_days(db, curator_group, today)
    students = _students(db, curator_group)
    marks = db.query(AttendanceMark).filter(AttendanceMark.student_id.in_([s.id for s in students])).all()
    assert len(marks) == len(days) * len(students)
    assert {m.mark_code.code for m in marks} == {"р"} and {m.date for m in marks} == set(days)
    assert db.query(AbsencePeriod).filter(AbsencePeriod.group_practice_id == practice["id"]).count() == len(students)


def test_practice_overwrites_manual_marks_and_reports_count(client, curator_headers, curator_group, curator_user, db, today):
    student = _students(db, curator_group)[0]
    day = _study_days(db, curator_group, today)[0]
    attendance_service.submit_day(
        db, curator_group.id, day, [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=day,
    )
    practice = _create(client, curator_headers, curator_group, today)
    assert practice["replaced_marks"] == 1
    mark = db.query(AttendanceMark).filter_by(student_id=student.id, date=day).one()
    assert mark.mark_code.code == "р"


def test_practice_does_not_put_students_to_risk_or_compensation(client, curator_headers, curator_group, curator_user, db, today):
    _create(client, curator_headers, curator_group, today)
    days = [d for d in _study_days(db, curator_group, today) if d <= today]
    for day in days:
        attendance_service.submit_day(db, curator_group.id, day, [], curator_user, today=day)
    students = attendance_service.get_active_students(db, curator_group.id, days[-1])
    rates = attendance_service.attendance_rates_bulk(db, students, days[-1])
    assert all(not r.is_risk and not r.needs_compensation and r.absent_to_compensate == 0 for r in rates.values())


def test_update_moves_marks_and_delete_removes_them(client, curator_headers, curator_group, db, today):
    practice = _create(client, curator_headers, curator_group, today)
    new_to = today - datetime.timedelta(days=3)
    r = client.put(f"/practice/{practice['id']}", headers=curator_headers, json=_body(today, date_to=new_to.isoformat()))
    assert r.status_code == 200, r.text
    assert db.query(AttendanceMark).filter(AttendanceMark.date > new_to).count() == 0
    assert db.query(AttendanceMark).count() > 0
    assert client.delete(f"/practice/{practice['id']}", headers=curator_headers).status_code == 204
    assert db.query(AttendanceMark).count() == 0 and db.query(AbsencePeriod).count() == 0
    assert db.query(GroupPractice).count() == 0


def test_student_period_of_practice_is_not_editable_directly(client, curator_headers, curator_group, db, today):
    practice = _create(client, curator_headers, curator_group, today)
    period = db.query(AbsencePeriod).filter(AbsencePeriod.group_practice_id == practice["id"]).first()
    body = {"mark_code": "р", "date_from": practice["date_from"], "date_to": practice["date_to"]}
    assert client.put(f"/curator/absence-periods/{period.id}", headers=curator_headers, json=body).status_code == 409
    assert client.delete(f"/curator/absence-periods/{period.id}", headers=curator_headers).status_code == 409


def test_student_who_joins_during_practice_gets_the_mark(client, curator_headers, curator_group, db, today):
    _create(client, curator_headers, curator_group, today)
    day = next(d for d in _study_days(db, curator_group, today) if d >= today - datetime.timedelta(days=1))
    new = Student(last_name="Новиков", first_name="Тест", study_group_id=curator_group.id, enrolled_at=today - datetime.timedelta(days=1))
    db.add(new)
    db.flush()
    group_membership_service.create_initial_membership(db, new)
    db.commit()
    assert db.query(AttendanceMark).filter_by(student_id=new.id).count() == 0
    r = client.get(f"/curator/groups/{curator_group.id}/day", headers=curator_headers, params={"date": day.isoformat()})
    assert r.status_code == 200, r.text
    entry = next(e for e in r.json()["entries"] if e["student_id"] == new.id)
    assert entry["mark_code"] == "р" and entry["is_locked"] and entry["absence_period"]["group_practice_id"] is not None
    assert db.query(AttendanceMark).filter_by(student_id=new.id).count() >= 1


def test_review_flag_sets_date_and_state(client, curator_headers, curator_group, today):
    past = dict(date_from=(today - datetime.timedelta(days=30)).isoformat(), date_to=(today - datetime.timedelta(days=10)).isoformat())
    practice = _create(client, curator_headers, curator_group, today, **past)
    assert practice["state"] == "no_review" and practice["review_received"] is False
    r = client.put(f"/practice/{practice['id']}", headers=curator_headers, json=_body(today, review_received=True, **past))
    # Дата получения — календарный «сегодня» сервера, а фикстура `today` в выходные даёт прошлый учебный день.
    assert r.json()["review_received_on"] == today_local().isoformat() and r.json()["state"] is None


def test_validation(client, curator_headers, curator_group, today):
    bad = _body(today, date_from=today.isoformat(), date_to=(today - datetime.timedelta(days=1)).isoformat())
    assert client.post(f"/practice/groups/{curator_group.id}", headers=curator_headers, json=bad).status_code == 400
    long = _body(today, date_to=(today + datetime.timedelta(days=400)).isoformat())
    assert client.post(f"/practice/groups/{curator_group.id}", headers=curator_headers, json=long).status_code == 400


def test_roles_matrix(client, curator_headers, curator_group, db_second_curator, dept_head_headers, edu_department_headers,
                      admin_headers, today):
    other = _login(client, db_second_curator.username, "SecondCura#58x!")
    url = f"/practice/groups/{curator_group.id}"
    # (заголовки, может ли менять, может ли читать)
    for name, headers, can_edit, can_view in [
        ("куратор группы", curator_headers, True, True),
        ("чужой куратор", other, False, False),
        ("зав. отделением", dept_head_headers, True, True),
        ("воспитательный отдел", edu_department_headers, True, True),
        ("админ", admin_headers, True, True),
    ]:
        got = client.get(url, headers=headers)
        assert (got.status_code == 200) is can_view, name
        if can_view:
            assert got.json()["can_edit"] is can_edit, name
        assert (client.post(url, headers=headers, json=_body(today)).status_code == 201) is can_edit, name


def test_summary_for_dept_head_and_closed_for_curator(client, curator_headers, curator_group, dept_head_headers, today):
    _create(client, curator_headers, curator_group, today)
    soon = dict(date_from=(today + datetime.timedelta(days=5)).isoformat(), date_to=(today + datetime.timedelta(days=20)).isoformat())
    _create(client, curator_headers, curator_group, today, **soon)
    rows = client.get("/practice/current", headers=dept_head_headers).json()
    assert [r["state"] for r in rows] == ["active", "soon"] and rows[0]["group_code"] == curator_group.code
    assert client.get("/practice/current", headers=curator_headers).status_code == 403
