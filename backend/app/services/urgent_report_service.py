from sqlalchemy.orm import Session, joinedload

from app.core import field_crypto, policies
from app.core.time import utcnow
from app.models import Role, RoleCode, Student, StudyGroup, UrgentReport, User
from app.schemas.students import UrgentReportRead
from app.services import in_app_notification_service
from app.services.audit_service import log_action

CATEGORY_TITLES = {"misconduct": "проступок", "offense": "правонарушение", "emergency": "ЧП"}


class UrgentReportError(Exception):
    pass


def recipients(db: Session, group: StudyGroup) -> list[User]:
    """Зав. отделением и воспитательный отдел отделения группы; без них — администраторы."""
    staff = []
    if group.department_id is not None:
        staff = (
            db.query(User)
            .filter(
                User.is_active.is_(True), User.department_id == group.department_id,
                User.role.has(Role.code.in_((RoleCode.DEPT_HEAD.value, RoleCode.EDU_DEPARTMENT.value))),
            )
            .all()
        )
    if staff:
        return staff
    return db.query(User).filter(User.role.has(code=RoleCode.ADMIN.value), User.is_active.is_(True)).all()


def to_read(report: UrgentReport, group_code: str, with_text: bool) -> UrgentReportRead:
    text = field_crypto.decrypt_json(report.text_enc)["text"] if with_text else None
    return UrgentReportRead(
        id=report.id, student_id=report.student_id, student_name=report.student.full_name, group_code=group_code,
        category=report.category, text=text, author_name=report.author.full_name, created_at=report.created_at,
        acknowledged_by_name=report.acknowledged_by.full_name if report.acknowledged_by else None,
        acknowledged_at=report.acknowledged_at,
    )


def _query(db: Session):
    return db.query(UrgentReport).options(
        joinedload(UrgentReport.student), joinedload(UrgentReport.author), joinedload(UrgentReport.acknowledged_by),
    )


def get(db: Session, report_id: int) -> UrgentReport | None:
    return _query(db).filter(UrgentReport.id == report_id).first()


def list_for_readers(db: Session, user: User, department_id: int | None, only_open: bool) -> list[UrgentReport]:
    q = _query(db).join(Student, UrgentReport.student_id == Student.id).join(StudyGroup, Student.study_group_id == StudyGroup.id)
    if department_id is not None:
        q = q.filter(StudyGroup.department_id == department_id)
    if only_open:
        q = q.filter(UrgentReport.acknowledged_at.is_(None))
    return q.order_by(UrgentReport.id.desc()).all()


def list_by_author(db: Session, user: User, student_id: int) -> list[UrgentReport]:
    return _query(db).filter(UrgentReport.student_id == student_id, UrgentReport.author_id == user.id).order_by(UrgentReport.id.desc()).all()


def create(db: Session, user: User, student: Student, category: str, text: str) -> UrgentReport:
    if not field_crypto.is_available():
        raise UrgentReportError("Не задан ключ шифрования: сообщение не сохранено")
    group = db.get(StudyGroup, student.study_group_id)
    report = UrgentReport(
        student_id=student.id, author_id=user.id, category=category,
        text_enc=field_crypto.encrypt_json({"text": text.strip()}),
    )
    db.add(report)
    db.flush()
    log_action(db, user, "urgent_report.create", "student", str(student.id), new_value=category)
    for staff in recipients(db, group):
        if staff.id != user.id:
            in_app_notification_service.notify(
                db, staff, "urgent_report",
                f"Срочное сообщение ({CATEGORY_TITLES[category]}): {student.full_name}, группа {group.code}. Откройте и примите.",
                entity_type="urgent_report", entity_id=str(report.id),
            )
    db.commit()
    return report


def acknowledge(db: Session, report: UrgentReport, reader: User) -> None:
    if report.acknowledged_at is not None:
        return
    report.acknowledged_by_user_id = reader.id
    report.acknowledged_at = utcnow()
    log_action(db, reader, "urgent_report.acknowledge", "student", str(report.student_id))
    in_app_notification_service.notify(
        db, report.author, "urgent_report_ack",
        f"{reader.full_name} принял(а) ваше срочное сообщение о студенте {report.student.full_name}.",
        entity_type="student", entity_id=str(report.student_id),
    )
    db.commit()
