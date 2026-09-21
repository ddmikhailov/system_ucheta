import datetime

import pytest

from app.models import AttendanceMark, BasisStatus, MarkCode, MarkSource
from app.services import attendance_service

DAY1 = datetime.date(2026, 9, 21)  # понедельник
DAY2 = datetime.date(2026, 9, 22)
DAY3 = datetime.date(2026, 9, 23)


def _mark_code(db, code: str) -> MarkCode:
    return db.query(MarkCode).filter(MarkCode.code == code).one()


def test_roster_before_any_submission_is_not_submitted(imported, db, curator_group):
    roster = attendance_service.get_roster(db, curator_group.id, DAY1)
    assert roster["is_submitted"] is False
    assert len(roster["entries"]) > 0
    assert all(e["mark_code"] is None for e in roster["entries"])


def test_submit_day_persists_exceptions_and_submission(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    s1, s2 = students[0], students[1]

    attendance_service.submit_day(
        db, curator_group.id, DAY1,
        [
            {"student_id": s1.id, "mark_code": "б", "comment": None, "basis_reference": None},
            {"student_id": s2.id, "mark_code": "н", "comment": None, "basis_reference": None},
        ],
        curator_user, today=DAY1,
    )

    roster = attendance_service.get_roster(db, curator_group.id, DAY1)
    assert roster["is_submitted"] is True
    assert roster["is_on_time"] is True

    by_id = {e["student_id"]: e for e in roster["entries"]}
    assert by_id[s1.id]["mark_code"] == "б"
    assert by_id[s2.id]["mark_code"] == "н"

    mark = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == s1.id, AttendanceMark.date == DAY1
    ).one()
    assert mark.basis_status == BasisStatus.PENDING
    assert mark.basis_deadline == DAY1 + datetime.timedelta(days=3)


def test_submitting_without_document_requiring_code_needs_no_basis(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    student = students[0]

    attendance_service.submit_day(
        db, curator_group.id, DAY1,
        [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=DAY1,
    )
    mark = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == student.id, AttendanceMark.date == DAY1
    ).one()
    assert mark.basis_status == BasisStatus.NOT_REQUIRED


def test_draft_copies_yesterdays_exceptions_but_does_not_persist(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    s1 = students[0]

    attendance_service.submit_day(
        db, curator_group.id, DAY1,
        [{"student_id": s1.id, "mark_code": "б", "comment": None, "basis_reference": None}],
        curator_user, today=DAY1,
    )

    draft_roster = attendance_service.get_roster(db, curator_group.id, DAY2)
    assert draft_roster["is_submitted"] is False
    by_id = {e["student_id"]: e for e in draft_roster["entries"]}
    assert by_id[s1.id]["mark_code"] == "б"
    assert by_id[s1.id]["is_draft_suggestion"] is True

    # "Все присутствуют" на day2 должно проигнорировать черновик.
    attendance_service.submit_day(db, curator_group.id, DAY2, [], curator_user, today=DAY2)
    submitted_roster = attendance_service.get_roster(db, curator_group.id, DAY2)
    by_id2 = {e["student_id"]: e for e in submitted_roster["entries"]}
    assert by_id2[s1.id]["mark_code"] is None


def test_curator_cannot_backdate_beyond_window(imported, db, curator_group, curator_user):
    far_future = DAY3 + datetime.timedelta(days=5)
    with pytest.raises(attendance_service.BackdateNotAllowed):
        attendance_service.submit_day(db, curator_group.id, DAY1, [], curator_user, today=far_future)


def test_dept_head_can_backdate_freely(imported, db, curator_group, dept_head_user):
    far_future = DAY3 + datetime.timedelta(days=5)
    # Не должно бросить исключение.
    attendance_service.submit_day(db, curator_group.id, DAY1, [], dept_head_user, today=far_future)
    roster = attendance_service.get_roster(db, curator_group.id, DAY1)
    assert roster["is_submitted"] is True
    assert roster["is_on_time"] is False  # сдано задним числом


def test_absence_period_overwrites_existing_mark(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    student = students[0]

    attendance_service.submit_day(
        db, curator_group.id, DAY1,
        [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=DAY1,
    )

    mark_code_b = _mark_code(db, "б")
    attendance_service.create_absence_period(
        db, student.id, mark_code_b.id, DAY1, DAY1, "Справка №1", curator_user
    )

    mark = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == student.id, AttendanceMark.date == DAY1
    ).one()
    assert mark.mark_code.code == "б"
    assert mark.source == MarkSource.PERIOD
    assert mark.basis_status == BasisStatus.CONFIRMED


def test_period_mark_is_preserved_across_day_resubmission(imported, db, curator_group, curator_user):
    """Предзаполненные периодом строки куратор не обязан включать в 'Сдать день'."""
    students = attendance_service.get_active_students(db, curator_group.id, DAY2)
    student = students[0]

    mark_code_b = _mark_code(db, "б")
    attendance_service.create_absence_period(
        db, student.id, mark_code_b.id, DAY2, DAY2, "Приказ №2", curator_user
    )

    # Куратор сдаёт день без упоминания этого студента — период не должен слететь.
    attendance_service.submit_day(db, curator_group.id, DAY2, [], curator_user, today=DAY2)

    mark = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == student.id, AttendanceMark.date == DAY2
    ).one()
    assert mark.mark_code.code == "б"
    assert mark.source == MarkSource.PERIOD


def test_consecutive_unexcused_count_resets_on_period_overwrite(imported, db, curator_group, curator_user):
    students = attendance_service.get_active_students(db, curator_group.id, DAY1)
    student = students[0]

    for day in (DAY1, DAY2, DAY3):
        attendance_service.submit_day(
            db, curator_group.id, day,
            [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
            curator_user, today=day,
        )

    streak = attendance_service.consecutive_unexcused_count(db, student.id, DAY3 + datetime.timedelta(days=1))
    assert streak == 3

    mark_code_b = _mark_code(db, "б")
    attendance_service.create_absence_period(
        db, student.id, mark_code_b.id, DAY2, DAY3, "Справка №9", curator_user
    )

    streak_after = attendance_service.consecutive_unexcused_count(db, student.id, DAY3 + datetime.timedelta(days=1))
    assert streak_after == 0
