"""Быстрые (пакетные) версии экранов дают те же числа, что построчные, и не делают
запросов на каждую группу/студента (см. CHANGELOG 2.0.2: «День по колледжу» делал
~1300 запросов, «Динамика» — загружала всех студентов заново на каждый день)."""
import datetime
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.models import (
    AttendanceMark, DaySubmission, DayType, GroupCalendarOverride, MarkCode, Student, StudyGroup, User,
)
from app.services import attendance_service, calendar_service, group_membership_service, stats_service


@contextmanager
def count_queries(db):
    counter = {"n": 0}

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)


@pytest.fixture()
def busy(imported, db, today):
    """Сданные дни и отметки у части групп, один студент переведён в другую группу
    и один выбыл — те самые случаи, на которых легко разойтись с построчным расчётом."""
    admin = db.query(User).filter_by(username="admin").one()
    n_code = db.query(MarkCode).filter_by(code="н").one()
    late_code = db.query(MarkCode).filter_by(code="о").one()
    groups = db.query(StudyGroup).order_by(StudyGroup.code).all()
    days = [today - datetime.timedelta(days=i) for i in range(0, 8)]
    for i, group in enumerate(groups[:20]):
        students = db.query(Student).filter_by(study_group_id=group.id).order_by(Student.id).all()
        for d in days:
            if (i + d.day) % 3 == 0:
                continue  # часть дней не сдана
            db.add(DaySubmission(study_group_id=group.id, date=d, submitted_by_user_id=admin.id, first_period=1))
            for k, student in enumerate(students[:4]):
                db.add(AttendanceMark(
                    student_id=student.id, date=d, created_by_user_id=admin.id,
                    mark_code_id=(late_code if k == 0 else n_code).id,
                ))
    movers = db.query(Student).filter_by(study_group_id=groups[0].id).order_by(Student.id).all()
    group_membership_service.transfer_student(db, movers[5], groups[1].id, today - datetime.timedelta(days=3), admin)
    movers[5].study_group_id = groups[1].id
    movers[6].left_at = today - datetime.timedelta(days=2)
    db.commit()
    return groups, days


def test_day_stats_bulk_matches_per_group_calculation(busy, db, today):
    groups, days = busy
    for day in (days[0], days[2], days[4]):
        bulk = stats_service.compute_day_stats_bulk(db, day, [g.id for g in groups])
        for group in groups:
            slow = stats_service.compute_period_stats(db, day, day, study_group_id=group.id)
            fast = bulk[group.id]
            assert (fast.in_list, fast.absent_total, fast.absent_excused, fast.absent_unexcused, fast.late, fast.by_code) == (
                slow.in_list, slow.absent_total, slow.absent_excused, slow.absent_unexcused, slow.late, slow.by_code,
            ), f"{group.code} {day}"
        assert any(b.in_list for b in bulk.values()) and any(b.absent_total for b in bulk.values())  # данные не пустые


def test_dynamics_fast_path_matches_per_day_for_college_department_and_course(busy, db, today):
    groups, days = busy
    date_from, date_to = min(days), max(days)
    department_id = groups[0].department_id
    for kwargs in ({}, {"department_id": department_id}, {"course": 1}, {"course": 2, "department_id": department_id}):
        fast = stats_service.dynamics(db, date_from, date_to, **kwargs)
        slow = stats_service._dynamics_per_day(
            db, date_from, date_to, kwargs.get("department_id"), kwargs.get("course"), None, None
        )
        assert fast == slow, kwargs
        assert any(row["percent"] is not None for row in slow) or kwargs.get("course") == 2  # есть дни с данными


def test_dynamics_for_one_group_or_student_still_uses_the_exact_path(busy, db):
    groups, days = busy
    rows = stats_service.dynamics(db, min(days), max(days), study_group_id=groups[0].id)
    assert rows == stats_service._dynamics_per_day(db, min(days), max(days), None, None, groups[0].id, None)


def test_study_days_by_group_matches_study_days_between(imported, db, today):
    group = db.query(StudyGroup).order_by(StudyGroup.code).first()
    holiday = today - datetime.timedelta(days=2)
    db.add(GroupCalendarOverride(study_group_id=group.id, date=holiday, day_type=DayType.HOLIDAY))
    db.commit()
    groups = db.query(StudyGroup).all()
    date_from, date_to = today - datetime.timedelta(days=21), today

    bulk = calendar_service.study_days_by_group(db, date_from, date_to, groups)

    for g in groups:
        assert bulk[g.id] == calendar_service.study_days_between(db, date_from, date_to, study_group_id=g.id, course=g.course)
    assert holiday not in bulk[group.id]


def test_streaks_bulk_match_the_single_student_calculation(busy, db, today):
    students = db.query(Student).limit(120).all()
    bulk = attendance_service.consecutive_unexcused_counts_bulk(db, students, today + datetime.timedelta(days=1))
    for student in students:
        single = attendance_service.consecutive_unexcused_count(
            db, student.id, today + datetime.timedelta(days=1), study_group_id=student.study_group_id
        )
        assert bulk[student.id] == single, student.id


def test_college_wide_screens_do_not_query_per_group(busy, db, today):
    date_from = today - datetime.timedelta(days=7)
    with count_queries(db) as q:
        rows = stats_service.day_overview(db, today)
    assert len(rows) >= 40 and q["n"] <= 12, q["n"]

    with count_queries(db) as q:
        stats_service.curator_discipline(db, date_from, today)
    assert q["n"] <= 12, q["n"]

    with count_queries(db) as q:
        stats_service.dynamics(db, date_from, today)
    assert q["n"] <= 12, q["n"]

    with count_queries(db) as q:
        stats_service.risk_students(db, today, 1)
    assert q["n"] <= 12, q["n"]


def test_roster_does_not_query_per_student(busy, db, today):
    group = db.query(StudyGroup).order_by(StudyGroup.code).first()
    with count_queries(db) as q:
        roster = attendance_service.get_roster(db, group.id, today)
    assert len(roster["entries"]) >= 20 and q["n"] <= 15, q["n"]
