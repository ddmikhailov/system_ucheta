"""Срочные сообщения куратора заведующему: отправка из карточки студента, список и приём для администрации отделения."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, get_current_user, require_roles, scope_department_id
from app.core import policies
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, Student, StudyGroup, User
from app.schemas.students import UrgentReportCreate, UrgentReportRead
from app.services import urgent_report_service as reports
from app.services.audit_service import log_action

router = APIRouter(prefix="/urgent-reports", tags=["urgent-reports"])

require_reader = require_roles(*policies.URGENT_REPORT_READERS)


def _group_code(db: Session, report) -> str:
    return db.get(StudyGroup, report.student.study_group_id).code


def _report_or_404(db: Session, report_id: int):
    report = reports.get(db, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")
    return report


@router.get("", response_model=list[UrgentReportRead])
def inbox(only_open: bool = False, user: User = Depends(require_reader), db: Session = Depends(get_db)):
    """Сообщения отделения: зав. отделением, тьютору и воспитательному отделу — своего, администратору — все."""
    department_id = scope_department_id(user, None)
    result = [reports.to_read(r, _group_code(db, r), with_text=True) for r in reports.list_for_readers(db, user, department_id, only_open)]
    for item in result:
        log_action(db, user, "urgent_report.view", "student", str(item.student_id))
    db.commit()
    return result


@router.get("/for-student/{student_id}", response_model=list[UrgentReportRead])
def for_student(student_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Свои сообщения по студенту — для карточки (статус «принято»). Текст автору не возвращается."""
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    assert_can_access_group(db, user, student.study_group_id, today_local())
    return [reports.to_read(r, _group_code(db, r), with_text=False) for r in reports.list_by_author(db, user, student_id)]


@router.post("", response_model=UrgentReportRead, status_code=status.HTTP_201_CREATED)
def create(payload: UrgentReportCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    student = db.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    assert_can_access_group(db, user, student.study_group_id, today_local())
    try:
        report = reports.create(db, user, student, payload.category, payload.text)
    except reports.UrgentReportError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return reports.to_read(_report_or_404(db, report.id), _group_code(db, report), with_text=False)


@router.post("/{report_id}/acknowledge", response_model=UrgentReportRead)
def acknowledge(report_id: int, user: User = Depends(require_reader), db: Session = Depends(get_db)):
    report = _report_or_404(db, report_id)
    policies.assert_can_read_urgent_report(user, db.get(StudyGroup, report.student.study_group_id))
    reports.acknowledge(db, report, user)
    return reports.to_read(_report_or_404(db, report_id), _group_code(db, report), with_text=True)
