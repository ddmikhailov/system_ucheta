"""End-to-end проверка временного эндпоинта разового импорта посещаемости
(см. app/api/routers/bulk_import.py) — двухфазность (сначала отчёт, потом
запись), отказ при ненайденных студентах/нераспознанных кодах, идемпотентность.

Эндпоинт использует today_local() (реальные часы), чтобы не дать записать
будущую дату — сентябрь 2026 при запуске тестов ещё не полностью прошёл,
поэтому "сегодня" фиксируем после конца месяца."""
import datetime
import io

import openpyxl
import pytest

from app.models import AttendanceMark, DaySubmission, MarkCode, Student


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    """Импорт — про уже прошедший сентябрь; без этого дни после реальной
    сегодняшней даты отклоняются как «ещё не наступившие» (см. can_edit_date)."""
    monkeypatch.setattr(
        "app.api.routers.bulk_import.today_local", lambda: datetime.date(2026, 10, 1)
    )


def _build_workbook(sheet_name: str, student_rows: list[tuple]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append((sheet_name, None, "Сентябрь"))
    ws.append((None,))
    header = ["№ п/п", "ФИО"] + list(range(1, 32))
    ws.append(header)
    for row in student_rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _student_row(no: int, fio: str, codes_by_day: dict[int, str]) -> tuple:
    row = [no, fio] + [None] * 31
    for day, code in codes_by_day.items():
        row[1 + day] = code
    return tuple(row)


def test_dry_run_reports_without_writing(client, admin_headers, curator_group, db):
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    data = _build_workbook(curator_group.code, [_student_row(1, student.full_name, {21: "н"})])  # DAY1 = Mon 2026-09-21

    r = client.post(
        "/admin/_temp-september-import", headers=admin_headers,
        files=[("files", ("test.xlsx", data, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] is False
    assert body["groups"][0]["group"] == curator_group.code
    assert body["groups"][0]["marks_total"] == 1

    assert db.query(AttendanceMark).count() == 0
    assert db.query(DaySubmission).count() == 0


def test_commit_writes_marks_and_submissions(client, admin_headers, curator_group, db):
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    data = _build_workbook(curator_group.code, [_student_row(1, student.full_name, {21: "н"})])

    r = client.post(
        "/admin/_temp-september-import?commit=true", headers=admin_headers,
        files=[("files", ("test.xlsx", data, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] is True
    assert body["marks_created"] == 1
    study_days = body["groups"][0]["study_days"]
    assert body["submissions_created"] == study_days  # один DaySubmission на каждый учебный день сентября

    mark = db.query(AttendanceMark).filter(AttendanceMark.student_id == student.id).one()
    assert mark.mark_code.code == "н"
    assert mark.created_by_user_id is not None  # приписано вызвавшему admin, не куратору

    assert db.query(DaySubmission).count() == study_days
    submission = (
        db.query(DaySubmission)
        .filter(DaySubmission.study_group_id == curator_group.id, DaySubmission.date == mark.date)
        .one()
    )
    assert submission.submitted_by_user_id == mark.created_by_user_id


def test_commit_refuses_when_student_not_found(client, admin_headers, curator_group, db):
    data = _build_workbook(curator_group.code, [_student_row(1, "Несуществующий Студент Иванович", {21: "н"})])

    r = client.post(
        "/admin/_temp-september-import?commit=true", headers=admin_headers,
        files=[("files", ("test.xlsx", data, "application/octet-stream"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] is False
    assert body["students_not_found"] == [{"group": curator_group.code, "student": "Несуществующий Студент Иванович"}]
    assert db.query(AttendanceMark).count() == 0


def test_commit_refuses_when_unrecognized_code(client, admin_headers, curator_group, db):
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    data = _build_workbook(curator_group.code, [_student_row(1, student.full_name, {21: "эл"})])

    r = client.post(
        "/admin/_temp-september-import?commit=true", headers=admin_headers,
        files=[("files", ("test.xlsx", data, "application/octet-stream"))],
    )
    body = r.json()
    assert body["written"] is False
    assert len(body["unrecognized_codes"]) == 1
    assert db.query(AttendanceMark).count() == 0


def test_unknown_group_code_reported(client, admin_headers, imported):
    data = _build_workbook("НЕТ-ТАКОЙ-ГРУППЫ", [_student_row(1, "Кто-То Кто-То", {21: "н"})])

    r = client.post(
        "/admin/_temp-september-import?commit=true", headers=admin_headers,
        files=[("files", ("test.xlsx", data, "application/octet-stream"))],
    )
    body = r.json()
    assert body["written"] is False
    assert "НЕТ-ТАКОЙ-ГРУППЫ" in body["groups_not_found"]


def test_curator_forbidden(client, curator_headers, curator_group):
    data = _build_workbook(curator_group.code, [])
    r = client.post(
        "/admin/_temp-september-import", headers=curator_headers,
        files=[("files", ("test.xlsx", data, "application/octet-stream"))],
    )
    assert r.status_code == 403
