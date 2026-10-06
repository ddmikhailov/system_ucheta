"""Группа риска по посещаемости: студент попадает туда, если с начала семестра посещает меньше 85 % занятий."""
import datetime

from app.core.config import get_settings
from app.models import Student
from app.services import attendance_service, calendar_service, individual_work_service, stats_service
from app.services.attendance_service import AttendanceRate

START = datetime.date(2026, 9, 21)


def _days(db, group, n):
    days = calendar_service.study_days_between(db, START, START + datetime.timedelta(days=60), study_group_id=group.id, course=group.course)
    assert len(days) >= n
    return days[:n]


def _submit(db, group, user, day, marks=None):
    exceptions = [{"student_id": sid, "mark_code": code, "comment": None, "basis_reference": None} for sid, code in (marks or {}).items()]
    attendance_service.submit_day(db, group.id, day, exceptions, user, today=day)


def _students(db, group, day):
    return attendance_service.get_active_students(db, group.id, day)


def _rates(db, group, day):
    students = _students(db, group, day)
    return students, attendance_service.attendance_rates_bulk(db, students, day)


def test_percent_counts_all_absences_but_not_lateness(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3, s4 = _students(db, curator_group, days[0])[:4]
    for i, day in enumerate(days):
        marks = {}
        if i in (0, 1):
            marks[s1.id] = "н"  # два пропуска без причины — 80 %
        if i == 2:
            marks[s2.id] = "н"
        if i == 3:
            marks[s2.id] = "б"  # больничный тоже пропуск: 2 из 10 — 80 %
        if i < 5:
            marks[s3.id] = "о"  # опоздания — присутствие
        _submit(db, curator_group, curator_user, day, marks)
    students, rates = _rates(db, curator_group, days[-1])
    assert (rates[s1.id].days, rates[s1.id].absent, rates[s1.id].percent) == (10, 2, 80.0)
    assert rates[s2.id].percent == 80.0 and rates[s3.id].percent == 100.0 and rates[s4.id].percent == 100.0
    assert rates[s1.id].is_risk and rates[s2.id].is_risk and not rates[s3.id].is_risk


def test_threshold_is_strict_85_percent(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 20)
    s1, s2 = _students(db, curator_group, days[0])[:2]
    for i, day in enumerate(days):
        marks = {}
        if i < 3:
            marks[s1.id] = "н"  # 3 из 20 — ровно 85 % → ещё не риск
        if i < 4:
            marks[s2.id] = "н"  # 4 из 20 — 80 % → риск
        _submit(db, curator_group, curator_user, day, marks)
    _, rates = _rates(db, curator_group, days[-1])
    assert rates[s1.id].percent == 85.0 and not rates[s1.id].is_risk
    assert rates[s2.id].percent == 80.0 and rates[s2.id].is_risk
    assert get_settings().risk_attendance_percent == 85.0


def test_too_few_submitted_days_never_make_a_risk(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 4)
    s1 = _students(db, curator_group, days[0])[0]
    for i, day in enumerate(days):
        _submit(db, curator_group, curator_user, day, {s1.id: "н"} if i == 0 else {})
    _, rates = _rates(db, curator_group, days[-1])
    assert rates[s1.id].days == 4 and rates[s1.id].percent == 75.0
    assert not rates[s1.id].is_risk  # меньше risk_min_days сданных дней — процент ещё случаен


def test_unsubmitted_days_do_not_count_and_semester_starts_fresh(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 6)
    s1 = _students(db, curator_group, days[0])[0]
    for i, day in enumerate(days[:5]):
        _submit(db, curator_group, curator_user, day, {s1.id: "н"} if i == 0 else {})
    _, rates = _rates(db, curator_group, days[5])  # шестой день не сдан
    assert (rates[s1.id].days, rates[s1.id].absent) == (5, 1)
    assert attendance_service.semester_start(datetime.date(2026, 10, 6)) == datetime.date(2026, 9, 1)
    assert attendance_service.semester_start(datetime.date(2027, 1, 20)) == datetime.date(2026, 9, 1)
    assert attendance_service.semester_start(datetime.date(2027, 2, 1)) == datetime.date(2027, 2, 1)
    assert attendance_service.semester_start(datetime.date(2027, 6, 30)) == datetime.date(2027, 2, 1)
    _, spring = _rates(db, curator_group, datetime.date(2027, 3, 1))
    assert spring[s1.id].days == 0 and spring[s1.id].percent is None and not spring[s1.id].is_risk  # новый семестр — с нуля


def test_risk_students_list_is_sorted_by_attendance_and_honours_threshold(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3 = _students(db, curator_group, days[0])[:3]
    for i, day in enumerate(days):
        marks = {}
        if i < 5:
            marks[s1.id] = "н"  # 50 %
        if i < 2:
            marks[s2.id] = "н"  # 80 %
        if i == 0:
            marks[s3.id] = "н"  # 90 %
        _submit(db, curator_group, curator_user, day, marks)
    as_of = days[-1]
    rows = [r for r in stats_service.risk_students(db, as_of) if r["student_id"] in (s1.id, s2.id, s3.id)]
    assert [r["student_id"] for r in rows] == [s1.id, s2.id]  # хуже — выше; 90 % не в списке
    assert (rows[0]["attendance_percent"], rows[0]["days"], rows[0]["absent"]) == (50.0, 10, 5)
    assert rows[0]["streak"] == 0 and rows[0]["group_code"] == curator_group.code
    stricter = [r["student_id"] for r in stats_service.risk_students(db, as_of, threshold=95.0)]
    assert s3.id in stricter  # порог можно поднять
    assert s2.id not in [r["student_id"] for r in stats_service.risk_students(db, as_of, threshold=60.0)]


def test_dashboards_endpoint_uses_percent_threshold(client, admin_headers, imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1 = _students(db, curator_group, days[0])[0]
    for i, day in enumerate(days):
        _submit(db, curator_group, curator_user, day, {s1.id: "н"} if i < 3 else {})  # 70 %
    r = client.get(f"/dashboards/risk-students?as_of_date={days[-1]}", headers=admin_headers)
    assert r.status_code == 200
    mine = next(x for x in r.json() if x["student_id"] == s1.id)
    assert mine["attendance_percent"] == 70.0 and mine["days"] == 10 and mine["absent"] == 3
    low = client.get(f"/dashboards/risk-students?as_of_date={days[-1]}&threshold=60", headers=admin_headers).json()
    assert s1.id not in [x["student_id"] for x in low]
    assert client.get(f"/dashboards/risk-students?as_of_date={days[-1]}&threshold=101", headers=admin_headers).status_code == 422


def test_journal_marks_risk_students_and_shows_percent(client, curator_headers, imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2 = _students(db, curator_group, days[0])[:2]
    for i, day in enumerate(days):
        _submit(db, curator_group, curator_user, day, {s1.id: "н"} if i < 3 else {})
    entries = {e["student_id"]: e for e in client.get(f"/curator/groups/{curator_group.id}/day?date={days[-1]}", headers=curator_headers).json()["entries"]}
    assert entries[s1.id]["is_risk"] is True and entries[s1.id]["attendance_percent"] == 70.0
    assert entries[s2.id]["is_risk"] is False and entries[s2.id]["attendance_percent"] == 100.0
    settings = client.get("/curator/settings", headers=curator_headers).json()
    assert settings == {"risk_attendance_percent": 85.0, "risk_min_days": 5}


def test_individual_work_overview_uses_percent_not_streak(client, curator_headers, imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2 = _students(db, curator_group, days[0])[:2]
    for i, day in enumerate(days):
        marks = {}
        if i in (1, 3, 5):
            marks[s1.id] = "н"  # три пропуска не подряд — раньше риска не было бы, теперь 70 % → риск
        if i == 9:
            marks[s2.id] = "н"  # последний день, но 90 %
        _submit(db, curator_group, curator_user, day, marks)
    rows = individual_work_service.group_overview(db, curator_group.id, days[-1])
    by_id = {r.student_id: r for r in rows}
    assert by_id[s1.id].is_risk and by_id[s1.id].attendance_percent == 70.0 and by_id[s1.id].needs_attention
    assert s2.id not in by_id  # ни риска, ни записей


def test_rates_query_count_does_not_grow_with_students(imported, db):
    from sqlalchemy import event

    students = db.query(Student).all()
    queries = []

    def count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        attendance_service.attendance_rates_bulk(db, students, START)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert len(students) > 500 and len(queries) <= 4, len(queries)
