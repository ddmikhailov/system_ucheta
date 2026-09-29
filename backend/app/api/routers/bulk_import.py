"""Разовый импорт посещаемости за сентябрь 2026 из Excel-таблиц, которые
кураторы вели до запуска платформы (см. обсуждение в чате — временный
эндпоинт, удалить после использования вместе с bulk_import_service.py).

Двухфазный: без ?commit=true — только разбор и отчёт, ничего не пишет в БД.
Если в отчёте есть ненайденные группы/студенты/нераспознанные коды — commit
всё равно откатывается (raise), чтобы нельзя было случайно записать частичные
данные, не увидев отчёт целиком (см. решение в чате: "показать и
остановиться")."""
import calendar
import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_full_access
from app.core.time import today_local
from app.db.session import get_db
from app.models import Student, StudyGroup, User
from app.services import attendance_service, bulk_import_service, calendar_service

router = APIRouter(prefix="/admin/_temp-september-import", tags=["temp-import"])


@router.post("")
async def import_september_attendance(
    files: list[UploadFile],
    commit: bool = False,
    year: int = 2026,
    month: int = 9,
    user: User = Depends(require_full_access),
    db: Session = Depends(get_db),
):
    report: dict = {
        "commit": commit,
        "groups_not_found": [],
        "students_not_found": [],  # [{group, student}]
        "unrecognized_codes": [],  # [{group, student, day, code}]
        "groups": [],  # [{group, students_matched, marks, submissions}]
    }

    days_in_month = calendar.monthrange(year, month)[1]

    parsed_sheets = []
    for f in files:
        content = await f.read()
        try:
            parsed_sheets.extend(bulk_import_service.parse_attendance_workbook(content))
        except Exception as exc:  # noqa: BLE001 — отчёт важнее точного типа при разборе чужого файла
            report["groups_not_found"].append(f"{f.filename}: не удалось прочитать файл ({exc})")

    plan: list[dict] = []  # накопленные данные для второй фазы (commit)

    for sheet in parsed_sheets:
        if sheet.error:
            report["groups_not_found"].append(f"{sheet.group_code}: {sheet.error}")
            continue

        group = db.query(StudyGroup).filter(StudyGroup.code == sheet.group_code).one_or_none()
        if group is None:
            report["groups_not_found"].append(sheet.group_code)
            continue

        for fio, day, code in sheet.unrecognized:
            report["unrecognized_codes"].append(
                {"group": sheet.group_code, "student": fio, "day": day, "code": code}
            )

        students = db.query(Student).filter(Student.study_group_id == group.id).all()
        student_by_name = {s.full_name: s for s in students}

        matched_marks: dict[int, dict[int, str]] = {}  # student_id -> {day: code}
        for fio, day_codes in sheet.marks_by_student.items():
            student = student_by_name.get(fio)
            if student is None:
                report["students_not_found"].append({"group": sheet.group_code, "student": fio})
                continue
            matched_marks[student.id] = day_codes

        study_days = calendar_service.study_days_between(
            db, datetime.date(year, month, 1), datetime.date(year, month, days_in_month),
            study_group_id=group.id, course=group.course,
        )

        marks_count = sum(len(d) for d in matched_marks.values())
        report["groups"].append(
            {
                "group": sheet.group_code,
                "students_with_marks": len(matched_marks),
                "marks_total": marks_count,
                "study_days": len(study_days),
            }
        )
        plan.append({"group": group, "matched_marks": matched_marks, "study_days": study_days})

    has_problems = bool(report["groups_not_found"] or report["students_not_found"] or report["unrecognized_codes"])

    if not commit or has_problems:
        report["written"] = False
        if commit and has_problems:
            report["refused_reason"] = (
                "Есть ненайденные группы/студенты или нераспознанные коды — ничего не записано. "
                "Исправьте и повторите."
            )
        return report

    # --- Фаза записи: только если commit=true и отчёт полностью чист ---
    # submit_day коммитит на каждый день сам по себе (не единая транзакция на
    # весь импорт) — если что-то упадёт на середине, останавливаемся сразу и
    # честно показываем, докуда дошло. Он идемпотентен по (группа, дата),
    # так что повторный запуск после исправления причины ничего не задвоит.
    today = today_local()
    submissions_created = 0
    marks_created = 0
    try:
        for item in plan:
            group = item["group"]
            for date in item["study_days"]:
                exceptions = [
                    {"student_id": sid, "mark_code": codes[date.day], "comment": None, "basis_reference": None}
                    for sid, codes in item["matched_marks"].items()
                    if date.day in codes
                ]
                attendance_service.submit_day(db, group.id, date, exceptions, user, today=today)
                submissions_created += 1
                marks_created += len(exceptions)
    except (attendance_service.InvalidSubmission, attendance_service.BackdateNotAllowed) as exc:
        report["written"] = "partial"
        report["stopped_at"] = {"group": group.code, "date": str(date), "error": str(exc)}
        report["submissions_created"] = submissions_created
        report["marks_created"] = marks_created
        return report

    report["written"] = True
    report["submissions_created"] = submissions_created
    report["marks_created"] = marks_created
    return report
