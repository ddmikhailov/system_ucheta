"""Правка прошлого сданного дня куратором — через проверку зав. отделением (интерфейс 3.2).

Куратор отправляет полный вариант дня (как при сдаче) и причину. В журнале до решения остаётся
сданный вариант; зав. отделением (тьютор отделения, администратор) видит, что именно меняется,
и одобряет — тогда отметки применяются от имени куратора, а «сдано вовремя» не меняется, — или
отклоняет с комментарием. Новый запрос на тот же день заменяет прежний ожидающий."""

import datetime
import json

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.time import utcnow
from app.models import AttendanceChangeRequest, AttendanceMark, RoleCode, StudyGroup, User
from app.models.enums import MarkSource
from app.schemas.curator import AttendanceChangeRead, MarkChange
from app.services import attendance_service, in_app_notification_service
from app.services.audit_service import log_action

PENDING = "pending"


class ChangeNotAllowed(Exception):
    pass


def _reviewers(db: Session, group: StudyGroup) -> list[User]:
    """Кому прийти уведомлению: зав. отделением группы; если его нет — администраторам."""
    head = in_app_notification_service.dept_head_for(db, group.department_id)
    if head is not None:
        return [head]
    return (
        db.query(User)
        .filter(User.role.has(code=RoleCode.ADMIN.value), User.is_active.is_(True))
        .all()
    )


def _changes(db: Session, req: AttendanceChangeRequest) -> list[MarkChange]:
    students = attendance_service.get_active_students(db, req.study_group_id, req.date)
    marks = {
        m.student_id: m
        for m in db.execute(
            select(AttendanceMark)
            .options(joinedload(AttendanceMark.mark_code))
            .where(AttendanceMark.student_id.in_([s.id for s in students]), AttendanceMark.date == req.date)
        ).scalars()
    }
    wanted = {e["student_id"]: e for e in json.loads(req.exceptions_json)}
    result = []
    for s in students:
        mark = marks.get(s.id)
        entry = wanted.get(s.id)
        if mark is not None and mark.source == MarkSource.PERIOD and entry is None:
            continue  # период отсутствия при сдаче не трогается
        before = mark.mark_code.code if mark else None
        after = entry["mark_code"] if entry else None
        details = bool(
            entry and mark and before == after
            and ((entry.get("comment") or None) != (mark.comment or None)
                 or (entry.get("basis_reference") or None) != (mark.basis_reference or None))
        )
        if before != after or details:
            result.append(MarkChange(student_id=s.id, full_name=s.full_name, from_code=before, to_code=after,
                                     details_changed=details))
    return result


def to_read(db: Session, req: AttendanceChangeRequest, with_changes: bool = True) -> AttendanceChangeRead:
    return AttendanceChangeRead(
        id=req.id,
        study_group_id=req.study_group_id,
        group_code=req.study_group.code,
        date=req.date,
        requested_by_id=req.requested_by_user_id,
        requested_by_name=req.requested_by.full_name,
        created_at=req.created_at,
        reason=req.reason,
        status=req.status,
        reviewed_by_name=req.reviewed_by.full_name if req.reviewed_by else None,
        reviewed_at=req.reviewed_at,
        review_comment=req.review_comment,
        first_period=req.first_period,
        # Изменения считаются против текущего журнала — для решённых запросов это уже не «было/станет».
        changes=_changes(db, req) if with_changes and req.status == PENDING else [],
    )


def _query(db: Session):
    return db.query(AttendanceChangeRequest).options(
        joinedload(AttendanceChangeRequest.study_group),
        joinedload(AttendanceChangeRequest.requested_by),
        joinedload(AttendanceChangeRequest.reviewed_by),
    )


def for_day(db: Session, study_group_id: int, date: datetime.date) -> tuple[AttendanceChangeRead | None, AttendanceChangeRead | None]:
    """Ожидающий запрос и последнее решение по дню — для экрана журнала."""
    rows = (
        _query(db)
        .filter(AttendanceChangeRequest.study_group_id == study_group_id, AttendanceChangeRequest.date == date)
        .order_by(AttendanceChangeRequest.id.desc())
        .all()
    )
    pending = next((r for r in rows if r.status == PENDING), None)
    decided = next((r for r in rows if r.status in ("approved", "rejected")), None)
    return (to_read(db, pending) if pending else None, to_read(db, decided, with_changes=False) if decided else None)


def create(
    db: Session, user: User, group: StudyGroup, date: datetime.date,
    exceptions: list[dict], first_period: int | None, reason: str,
) -> AttendanceChangeRequest:
    if not attendance_service.edit_requires_review(db, user, group.id, date):
        raise ChangeNotAllowed("Этот день можно исправить сразу, без проверки — сохраните его обычным образом.")
    attendance_service.validate_exceptions(db, group.id, date, exceptions)
    for old in (
        db.query(AttendanceChangeRequest)
        .filter(
            AttendanceChangeRequest.study_group_id == group.id,
            AttendanceChangeRequest.date == date,
            AttendanceChangeRequest.status == PENDING,
        )
        .all()
    ):
        old.status = "cancelled"
        old.reviewed_at = utcnow()
        old.review_comment = "Заменён новым запросом"
    req = AttendanceChangeRequest(
        study_group_id=group.id, date=date, requested_by_user_id=user.id,
        exceptions_json=json.dumps(exceptions, ensure_ascii=False), first_period=first_period, reason=reason.strip(),
    )
    db.add(req)
    db.flush()
    log_action(db, user, "day.change_request", "attendance_change", str(req.id), new_value=f"{group.id}:{date}")
    for reviewer in _reviewers(db, group):
        if reviewer.id == user.id:
            continue
        in_app_notification_service.notify(
            db, reviewer, "attendance_change",
            f"{user.full_name} просит исправить посещаемость группы {group.code} за {date.strftime('%d.%m.%Y')}: "
            f"{reason.strip()[:200]}",
            entity_type="study_group_day", entity_id=f"{group.id}:{date.isoformat()}",
        )
    db.commit()
    return req


def get(db: Session, request_id: int) -> AttendanceChangeRequest | None:
    return _query(db).filter(AttendanceChangeRequest.id == request_id).one_or_none()


def list_pending(db: Session, department_id: int | None) -> list[AttendanceChangeRequest]:
    q = _query(db).filter(AttendanceChangeRequest.status == PENDING)
    if department_id is not None:
        q = q.join(StudyGroup, StudyGroup.id == AttendanceChangeRequest.study_group_id).filter(
            StudyGroup.department_id == department_id
        )
    return q.order_by(AttendanceChangeRequest.created_at).all()


def _decide(db: Session, req: AttendanceChangeRequest, reviewer: User, status: str, comment: str | None) -> None:
    if req.status != PENDING:
        raise ChangeNotAllowed("Запрос уже решён или отозван")
    req.status = status
    req.reviewed_by_user_id = reviewer.id
    req.reviewed_at = utcnow()
    req.review_comment = (comment or "").strip() or None


def approve(db: Session, req: AttendanceChangeRequest, reviewer: User, comment: str | None) -> None:
    _decide(db, req, reviewer, "approved", comment)
    log_action(db, reviewer, "day.change_approve", "attendance_change", str(req.id))
    in_app_notification_service.notify(
        db, req.requested_by, "attendance_change_approved",
        f"Исправление посещаемости {req.study_group.code} за {req.date.strftime('%d.%m.%Y')} одобрено"
        + (f": {req.review_comment}" if req.review_comment else ""),
        entity_type="study_group_day", entity_id=f"{req.study_group_id}:{req.date.isoformat()}",
    )
    # Отметки — от имени куратора, который их внёс; submit_day сохраняет всё одним коммитом.
    attendance_service.submit_day(
        db, req.study_group_id, req.date, json.loads(req.exceptions_json), req.requested_by,
        first_period=req.first_period, applying_approved_change=True,
    )


def reject(db: Session, req: AttendanceChangeRequest, reviewer: User, comment: str | None) -> None:
    if not (comment or "").strip():
        raise ChangeNotAllowed("Напишите, почему исправление отклонено")
    _decide(db, req, reviewer, "rejected", comment)
    log_action(db, reviewer, "day.change_reject", "attendance_change", str(req.id))
    in_app_notification_service.notify(
        db, req.requested_by, "attendance_change_rejected",
        f"Исправление посещаемости {req.study_group.code} за {req.date.strftime('%d.%m.%Y')} отклонено: "
        f"{req.review_comment}",
        entity_type="study_group_day", entity_id=f"{req.study_group_id}:{req.date.isoformat()}",
    )
    db.commit()


def cancel(db: Session, req: AttendanceChangeRequest, user: User) -> None:
    if req.requested_by_user_id != user.id:
        raise ChangeNotAllowed("Отозвать запрос может только тот, кто его отправил")
    if req.status != PENDING:
        raise ChangeNotAllowed("Запрос уже решён или отозван")
    req.status = "cancelled"
    req.reviewed_at = utcnow()
    log_action(db, user, "day.change_cancel", "attendance_change", str(req.id))
    db.commit()
