"""Посещаемость студента по месяцам (GET /students/{id}/attendance) и разбор
дисциплины куратора по дням для зав. отделением
(GET /dashboards/curator-discipline/{group}/days)."""
import datetime

from app.core.time import utc_to_local
from app.models import DaySubmission, Department, Role, RoleCode, Student, StudyGroup, User
from app.services import attendance_service, calendar_service


def _admin(db):
    return db.query(User).join(Role).filter(Role.code == RoleCode.ADMIN.value).one()


def _recent_study_days(db, group, today, count):
    days, day = [], today
    while len(days) < count:
        if calendar_service.is_study_day(db, day, study_group_id=group.id, course=group.course):
            days.append(day)
        day -= datetime.timedelta(days=1)
        assert (today - day).days < 60
    return days


def test_month_attendance_present_mark_and_not_submitted(client, curator_headers, db, curator_group, today):
    submitted_day, marked_day, missed_day = _recent_study_days(db, curator_group, today, 3)
    student = attendance_service.get_active_students(db, curator_group.id, marked_day)[0]
    admin = _admin(db)

    attendance_service.submit_day(db, curator_group.id, submitted_day, [], admin)
    attendance_service.submit_day(
        db, curator_group.id, marked_day,
        [{"student_id": student.id, "mark_code": "б", "comment": "справка", "basis_reference": "№5"}],
        admin,
    )

    months = {(d.year, d.month) for d in (submitted_day, marked_day, missed_day)}
    by_date = {}
    for year, month in months:
        r = client.get(f"/students/{student.id}/attendance?year={year}&month={month}", headers=curator_headers)
        assert r.status_code == 200, r.text
        for d in r.json()["days"]:
            by_date[d["date"]] = d
        assert r.json()["first_month"] == student.enrolled_at.strftime("%Y-%m")

    assert by_date[str(submitted_day)]["status"] == "present"
    assert by_date[str(marked_day)]["status"] == "mark"
    assert by_date[str(marked_day)]["mark_code"] == "б"
    assert by_date[str(marked_day)]["comment"] == "справка"
    assert by_date[str(marked_day)]["basis_reference"] == "№5"
    assert by_date[str(missed_day)]["status"] == "not_submitted"


def test_month_attendance_summary_counts(client, admin_headers, db, curator_group, today):
    day_a, day_b = _recent_study_days(db, curator_group, today, 2)
    student = attendance_service.get_active_students(db, curator_group.id, day_a)[0]
    admin = _admin(db)
    attendance_service.submit_day(db, curator_group.id, day_b, [], admin)
    attendance_service.submit_day(
        db, curator_group.id, day_a,
        [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        admin,
    )
    if (day_a.year, day_a.month) != (day_b.year, day_b.month):
        return  # дни попали в разные месяцы — сводку проверит другой прогон

    r = client.get(f"/students/{student.id}/attendance?year={day_a.year}&month={day_a.month}", headers=admin_headers)
    summary = r.json()["summary"]
    assert summary["study_days"] == 2
    assert summary["present"] == 1
    assert summary["absent"] == 1
    assert summary["absent_unexcused"] == 1
    assert summary["percent"] == 50.0
    assert summary["by_code"] == {"н": 1}


def test_month_attendance_skips_days_before_enrollment_and_future(client, admin_headers, db, curator_group, today):
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    student.enrolled_at = today - datetime.timedelta(days=3)
    db.commit()

    r = client.get(f"/students/{student.id}/attendance?year={today.year}&month={today.month}", headers=admin_headers)
    days = {d["date"]: d for d in r.json()["days"]}
    assert str(today + datetime.timedelta(days=1)) not in days  # будущее не показываем
    early = today - datetime.timedelta(days=5)
    if early.month == today.month:
        assert days[str(early)]["day_type"] == "not_enrolled"
        assert days[str(early)]["status"] == "none"


def test_month_attendance_rejects_bad_month(client, admin_headers, db, curator_group):
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    assert client.get(f"/students/{student.id}/attendance?year=2026&month=13", headers=admin_headers).status_code == 400


def _foreign_department_head(db):
    from app.core.security import hash_password

    other = Department(name="Другое отделение")
    db.add(other)
    db.flush()
    role = db.query(Role).filter(Role.code == RoleCode.DEPT_HEAD.value).one()
    user = User(
        username="chuzhoy_zav", full_name="Чужой зав", role_id=role.id, department_id=other.id,
        password_hash=hash_password("ChuzhoyZav123!"),
    )
    db.add(user)
    db.commit()
    return user


def test_curator_days_for_dept_head(client, dept_head_headers, db, curator_group, today):
    on_time_day, late_day, missed_day = _recent_study_days(db, curator_group, today, 3)
    admin = _admin(db)
    attendance_service.submit_day(db, curator_group.id, late_day, [], admin, first_period=2)
    attendance_service.submit_day(db, curator_group.id, on_time_day, [], admin, today=on_time_day, first_period=1)
    # is_on_time считается как «сдано в день занятия» — для not-today дня
    # проверяем через явный today.
    first_day = min(on_time_day, late_day, missed_day)

    r = client.get(
        f"/dashboards/curator-discipline/{curator_group.id}/days?date_from={first_day}&date_to={today}",
        headers=dept_head_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["group_code"] == curator_group.code
    assert body["responsible_name"]
    days = {d["date"]: d for d in body["days"]}

    assert days[str(on_time_day)]["status"] == "on_time"
    assert days[str(on_time_day)]["first_period"] == 1
    assert days[str(on_time_day)]["submitted_by"] == admin.full_name
    assert days[str(late_day)]["status"] == "late"
    assert days[str(late_day)]["days_late"] is not None
    assert days[str(missed_day)]["status"] == "missed"
    assert days[str(missed_day)]["submitted_at_local"] is None
    assert body["on_time"] == 1 and body["late"] == 1
    assert body["missed"] == body["total_study_days"] - 2
    assert body["average_on_time_submission"] is not None


def test_curator_days_time_is_converted_to_local(client, dept_head_headers, db, curator_group, today):
    day = _recent_study_days(db, curator_group, today, 1)[0]
    attendance_service.submit_day(db, curator_group.id, day, [], _admin(db), today=day)
    submission = db.query(DaySubmission).filter(DaySubmission.study_group_id == curator_group.id).one()
    submission.submitted_at = datetime.datetime(day.year, day.month, day.day, 6, 30)  # 06:30 UTC
    db.commit()

    r = client.get(
        f"/dashboards/curator-discipline/{curator_group.id}/days?date_from={day}&date_to={day}",
        headers=dept_head_headers,
    )
    local = r.json()["days"][0]["submitted_at_local"]
    expected = utc_to_local(datetime.datetime(day.year, day.month, day.day, 6, 30))
    assert local.startswith(expected.strftime("%Y-%m-%dT%H:%M"))
    assert r.json()["average_on_time_submission"] == expected.strftime("%H:%M")


def test_curator_days_only_for_dept_head_of_that_department(
    client, admin_headers, curator_headers, dept_head_headers, db, curator_group, today
):
    url = f"/dashboards/curator-discipline/{curator_group.id}/days?date_from={today}&date_to={today}"
    assert client.get(url, headers=curator_headers).status_code == 403
    assert client.get(url, headers=admin_headers).status_code == 403  # по просьбе: только зав. отделением

    _foreign_department_head(db)
    login = client.post("/auth/login", json={"username": "chuzhoy_zav", "password": "ChuzhoyZav123!"})
    assert login.status_code == 200, login.text
    foreign_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(url, headers=foreign_headers).status_code == 403

    assert client.get(url, headers=dept_head_headers).status_code == 200
    assert client.get(
        f"/dashboards/curator-discipline/999999/days?date_from={today}&date_to={today}", headers=dept_head_headers
    ).status_code == 404
