"""Запросы куратора на полное удаление студента: создать, одобрить (стирает студента), отклонить, отозвать."""
from sqlalchemy.orm import Session, joinedload

from app.core import policies
from app.core.time import utcnow
from app.models import RoleCode, Student, StudentDeletionRequest, StudentStatus, StudyGroup, User
from app.schemas.students import StudentDeletionRead
from app.services import in_app_notification_service
from app.services.audit_service import log_action
from app.services.erasure_service import delete_student_completely

PENDING = "pending"


class DeletionNotAllowed(Exception):
    pass


def _group(db: Session, student: Student) -> StudyGroup:
    return db.get(StudyGroup, student.study_group_id)


def _reviewers(db: Session, group: StudyGroup) -> list[User]:
    head = in_app_notification_service.dept_head_for(db, group.department_id)
    if head is not None:
        return [head]
    return db.query(User).filter(User.role.has(code=RoleCode.ADMIN.value), User.is_active.is_(True)).all()


def to_read(req: StudentDeletionRequest, group_code: str) -> StudentDeletionRead:
    return StudentDeletionRead(
        id=req.id, student_id=req.student_id, student_name=req.student.full_name, group_code=group_code,
        reason=req.reason, status=req.status, requested_by_name=req.requested_by.full_name,
        created_at=req.created_at, review_comment=req.review_comment,
    )


def _query(db: Session):
    return db.query(StudentDeletionRequest).options(
        joinedload(StudentDeletionRequest.student), joinedload(StudentDeletionRequest.requested_by)
    )


def get(db: Session, request_id: int) -> StudentDeletionRequest | None:
    return _query(db).filter(StudentDeletionRequest.id == request_id).one_or_none()


def list_pending(db: Session, department_id: int | None) -> list[StudentDeletionRequest]:
    q = _query(db).filter(StudentDeletionRequest.status == PENDING)
    if department_id is not None:
        q = q.join(Student, Student.id == StudentDeletionRequest.student_id).join(
            StudyGroup, StudyGroup.id == Student.study_group_id
        ).filter(StudyGroup.department_id == department_id)
    return q.order_by(StudentDeletionRequest.created_at).all()


def latest_for_student(db: Session, student_id: int) -> StudentDeletionRequest | None:
    return (
        _query(db).filter(StudentDeletionRequest.student_id == student_id)
        .order_by(StudentDeletionRequest.id.desc()).first()
    )


def create(db: Session, user: User, student: Student, reason: str) -> StudentDeletionRequest:
    if user.role.code in policies.FORCE_DELETE_ROLES:
        raise DeletionNotAllowed("У вас есть право удалить студента сразу — запрос не нужен")
    if student.status == StudentStatus.STUDYING:
        raise DeletionNotAllowed("Сначала студента нужно отчислить или перевести в академ. отпуск")
    existing = latest_for_student(db, student.id)
    if existing is not None and existing.status == PENDING:
        raise DeletionNotAllowed("Запрос на удаление этого студента уже ждёт решения")
    req = StudentDeletionRequest(student_id=student.id, requested_by_user_id=user.id, reason=reason.strip())
    db.add(req)
    db.flush()
    group = _group(db, student)
    log_action(db, user, "student.delete_request", "student", str(student.id))
    for reviewer in _reviewers(db, group):
        if reviewer.id != user.id:
            in_app_notification_service.notify(
                db, reviewer, "student_deletion",
                f"{user.full_name} просит удалить студента из группы {group.code} навсегда: {req.reason[:200]}",
                entity_type="student", entity_id=str(student.id),
            )
    db.commit()
    return req


def _decide(db: Session, req: StudentDeletionRequest, reviewer: User, status: str, comment: str | None) -> None:
    if req.status != PENDING:
        raise DeletionNotAllowed("Запрос уже рассмотрен")
    req.status = status
    req.reviewed_by_user_id = reviewer.id
    req.reviewed_at = utcnow()
    req.review_comment = comment.strip() if comment else None


def approve(db: Session, req: StudentDeletionRequest, reviewer: User) -> str:
    """Стирает студента целиком; строка запроса уходит вместе с ним, след остаётся в журнале действий."""
    if req.status != PENDING:
        raise DeletionNotAllowed("Запрос уже рассмотрен")
    student = db.get(Student, req.student_id)
    if student.status == StudentStatus.STUDYING:
        raise DeletionNotAllowed("Студент снова учится — удалить его нельзя")
    log_action(db, reviewer, "student.delete_request_approved", "student", str(student.id))
    return delete_student_completely(db, reviewer, student)


def reject(db: Session, req: StudentDeletionRequest, reviewer: User, comment: str | None) -> None:
    _decide(db, req, reviewer, "rejected", comment)
    in_app_notification_service.notify(
        db, req.requested_by, "student_deletion",
        f"Запрос на удаление студента отклонён{': ' + req.review_comment if req.review_comment else ''}",
        entity_type="student", entity_id=str(req.student_id),
    )
    log_action(db, reviewer, "student.delete_request_rejected", "student", str(req.student_id))
    db.commit()


def cancel(db: Session, req: StudentDeletionRequest, user: User) -> None:
    if req.requested_by_user_id != user.id:
        raise DeletionNotAllowed("Отозвать запрос может только его автор")
    _decide(db, req, user, "cancelled", None)
    db.commit()
