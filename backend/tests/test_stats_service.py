import datetime

from app.services import attendance_service, stats_service

DAY1 = datetime.date(2026, 9, 21)


def test_compute_period_stats_percent_with_no_marks(imported, db, curator_group):
    stats = stats_service.compute_period_stats(db, DAY1, DAY1, study_group_id=curator_group.id)
    expected = len(attendance_service.get_active_students(db, curator_group.id, DAY1))
    assert stats.in_list == expected
    assert stats.absent_total == 0
    assert stats.percent == 100.0


def test_compute_period_stats_counts_absences(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    s1, s2 = students[0], students[1]

    attendance_service.submit_day(
        db, curator_group.id, DAY1,
        [
            {"student_id": s1.id, "mark_code": "н", "comment": None, "basis_reference": None},
            {"student_id": s2.id, "mark_code": "о", "comment": None, "basis_reference": None},
        ],
        curator_user, today=DAY1,
    )

    stats = stats_service.compute_period_stats(db, DAY1, DAY1, study_group_id=curator_group.id)
    assert stats.absent_total == 1  # опоздание считается присутствием
    assert stats.absent_unexcused == 1
    assert stats.late == 1
    assert stats.present == stats.in_list - 1


def test_day_overview_reflects_submission_status(imported, db, curator_group, curator_user):
    rows = stats_service.day_overview(db, DAY1)
    row = next(r for r in rows if r["study_group_id"] == curator_group.id)
    assert row["is_submitted"] is False

    attendance_service.submit_day(db, curator_group.id, DAY1, [], curator_user, today=DAY1)

    rows_after = stats_service.day_overview(db, DAY1)
    row_after = next(r for r in rows_after if r["study_group_id"] == curator_group.id)
    assert row_after["is_submitted"] is True
    assert row_after["is_on_time"] is True


def test_curator_discipline_counts_missed_days(imported, db, curator_group, curator_user):
    date_from = DAY1
    date_to = DAY1 + datetime.timedelta(days=4)  # захватывает выходные

    attendance_service.submit_day(db, curator_group.id, DAY1, [], curator_user, today=DAY1)

    rows = stats_service.curator_discipline(db, date_from, date_to)
    row = next(r for r in rows if r["study_group_id"] == curator_group.id)
    assert row["on_time"] == 1
    assert row["missed"] == row["total_study_days"] - 1


def test_risk_students_threshold(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    student = students[0]

    for offset in range(3):
        day = DAY1 + datetime.timedelta(days=offset)
        attendance_service.submit_day(
            db, curator_group.id, day,
            [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
            curator_user, today=day,
        )

    # as_of_date — последний размеченный день; risk_students сам заглядывает на день
    # вперёд, чтобы включить его в подсчёт стрика (см. stats_service.risk_students).
    as_of = DAY1 + datetime.timedelta(days=2)
    risky = stats_service.risk_students(db, as_of, threshold=3)
    assert any(r["student_id"] == student.id for r in risky)

    not_risky = stats_service.risk_students(db, as_of, threshold=4)
    assert not any(r["student_id"] == student.id for r in not_risky)


def test_risk_students_query_count_does_not_scale_with_student_count(imported, db):
    """Раньше risk_students делала ~4 запроса НА КАЖДОГО студента колледжа
    (3959 запросов на 989 студентах, см. TODO.md 5) — теперь запросы
    батчатся по группе, так что их число зависит от количества групп,
    а не студентов."""
    from sqlalchemy import event

    queries = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _count)
    try:
        stats_service.risk_students(db, DAY1, threshold=3)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _count)

    # 44 группы в синтетическом наборе — раньше тут было бы под 4000 запросов.
    assert len(queries) < 200
