import datetime

import openpyxl

from app.models import AttendanceMark, DaySubmission, MarkSource, Role, RoleCode, User
from app.services import attendance_service
from scripts import import_attendance_xlsx as importer

D1 = datetime.date(2026, 9, 21)  # понедельник
D2 = datetime.date(2026, 9, 22)
D3 = datetime.date(2026, 9, 23)


def _admin(db) -> User:
    return db.query(User).join(Role).filter(Role.code == RoleCode.ADMIN.value).first()


def _write_xlsx(path, group_code, rows, days):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Отметки"
    ws.append(["Группа", "Студент", "Дата", "Код"])
    for row in rows:
        ws.append([group_code, *row])
    ws = wb.create_sheet("Дни")
    ws.append(["Группа", "Дата", "Статус"])
    for day, status in days:
        ws.append([group_code, day, status])
    wb.save(path)


def test_wipes_old_and_loads_filled_days_only(imported, db, curator_group, curator_user, tmp_path):
    students = attendance_service.get_active_students(db, curator_group.id, D1)
    s1, s2 = students[0], students[1]
    attendance_service.submit_day(
        db, curator_group.id, D1, [{"student_id": s2.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=D1,
    )

    path = tmp_path / "a.xlsx"
    _write_xlsx(
        path, curator_group.code,
        [(s1.full_name, D1, "б"), ("Несуществующий Студент Тестович", D1, "н")],
        [(D1, "заполнено"), (D2, "не заполнено"), (D3, "заполнено")],
    )

    report = importer.load(db, str(path), _admin(db), commit=True)

    marks = db.query(AttendanceMark).filter(AttendanceMark.date == D1).all()
    assert {(m.student_id, m.mark_code.code) for m in marks} == {(s1.id, "б")}
    assert report["deleted_marks"] == 1
    submitted = {s.date for s in db.query(DaySubmission).filter(DaySubmission.study_group_id == curator_group.id)}
    assert submitted == {D1, D3}
    assert report["students_not_found"] == [(curator_group.code, "Несуществующий Студент Тестович")]


def test_dry_run_writes_nothing(imported, db, curator_group, tmp_path):
    s1 = attendance_service.get_active_students(db, curator_group.id, D1)[0]
    path = tmp_path / "a.xlsx"
    _write_xlsx(path, curator_group.code, [(s1.full_name, D1, "б")], [(D1, "заполнено")])

    report = importer.load(db, str(path), _admin(db), commit=False)

    assert report["days_submitted"] == 1 and report["marks_written"] == 1
    assert db.query(AttendanceMark).count() == 0
    assert db.query(DaySubmission).count() == 0


def test_period_marks_are_kept(imported, db, curator_group, curator_user, tmp_path):
    s1 = attendance_service.get_active_students(db, curator_group.id, D1)[0]
    mark = AttendanceMark(
        student_id=s1.id, date=D1, mark_code_id=attendance_service.get_mark_codes(db)["б"].id,
        source=MarkSource.PERIOD, created_by_user_id=curator_user.id,
    )
    db.add(mark)
    db.commit()
    path = tmp_path / "a.xlsx"
    _write_xlsx(path, curator_group.code, [], [(D1, "заполнено")])

    report = importer.load(db, str(path), _admin(db), commit=True)

    assert report["kept_period_marks"] == 1
    assert db.query(AttendanceMark).filter(AttendanceMark.source == MarkSource.PERIOD).count() == 1
