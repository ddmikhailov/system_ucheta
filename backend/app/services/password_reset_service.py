"""Восстановление пароля: человек просит о нём с экрана входа, а выдают пароль те, кто вправе менять его
пароль (админ, зав. отделением, тьютор, воспитательный отдел — каждый в своих границах, см.
policies.assert_can_manage_user). Платформа сама никого не идентифицирует: получатель убеждается, что просит
именно этот человек, и передаёт временный пароль вне платформы."""
import datetime

from sqlalchemy.orm import Session, joinedload

from app.core import policies
from app.core.time import utcnow
from app.models import InAppNotification, PasswordResetRequest, RoleCode, User
from app.services import in_app_notification_service

NOTIFICATION_KIND = "password_reset"
NOTIFICATION_ENTITY = "password_reset"
# Повторное нажатие не плодит уведомления: пока запрос открыт, новое — не чаще раза в этот срок.
REPEAT_AFTER = datetime.timedelta(hours=1)
_RESPONDER_ROLES = (RoleCode.ADMIN, RoleCode.DEPT_HEAD, RoleCode.TUTOR, RoleCode.EDU_DEPARTMENT)


def responders(db: Session, target: User) -> list[User]:
    """Активные пользователи, которые могут выдать пароль этому человеку."""
    candidates = (
        db.query(User).options(joinedload(User.role))
        .filter(User.is_active.is_(True), User.id != target.id)
        .all()
    )
    return [u for u in candidates if RoleCode(u.role.code) in _RESPONDER_ROLES and policies.can_manage_user(u, target)]


def open_request(db: Session, target: User, ip: str | None) -> PasswordResetRequest | None:
    """Создаёт запрос и рассылает уведомления (без commit). None — если уведомлять рано (недавний
    запрос ещё открыт) или некому."""
    now = utcnow()
    pending = (
        db.query(PasswordResetRequest)
        .filter(PasswordResetRequest.user_id == target.id, PasswordResetRequest.status == "pending")
        .order_by(PasswordResetRequest.created_at.desc()).first()
    )
    if pending is not None and now - pending.created_at < REPEAT_AFTER:
        return None
    people = responders(db, target)
    if not people:
        return None
    request = PasswordResetRequest(user_id=target.id, requested_ip=ip)
    db.add(request)
    db.flush()
    department = target.department.name if target.department else None
    who = f"{target.full_name} ({target.role.name}" + (f", {department}" if department else "") + f", логин {target.username})"
    for person in people:
        in_app_notification_service.notify(
            db, person, NOTIFICATION_KIND,
            f"{who} просит восстановить пароль. Выдайте временный пароль в разделе «Пользователи».",
            entity_type=NOTIFICATION_ENTITY, entity_id=str(target.id),
        )
    return request


def close_requests(db: Session, target: User, resolver: User) -> int:
    """Временный пароль выдан: запрос закрывается, чужие уведомления гаснут (без commit)."""
    now = utcnow()
    pending = (
        db.query(PasswordResetRequest)
        .filter(PasswordResetRequest.user_id == target.id, PasswordResetRequest.status == "pending").all()
    )
    for request in pending:
        request.status = "done"
        request.resolved_at = now
        request.resolved_by = resolver.id
    if not pending:
        return 0
    for note in db.query(InAppNotification).filter(
        InAppNotification.kind == NOTIFICATION_KIND, InAppNotification.entity_type == NOTIFICATION_ENTITY,
        InAppNotification.entity_id == str(target.id), InAppNotification.read_at.is_(None),
    ):
        note.message = f"{target.full_name}: временный пароль выдан ({resolver.full_name})."[:500]
        note.read_at = now
    return len(pending)
