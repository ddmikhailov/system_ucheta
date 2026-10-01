import datetime

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import InAppNotification, RoleCode, StudyGroup, User


def notify(
    db: Session, user: User, kind: str, message: str,
    entity_type: str | None = None, entity_id: str | None = None,
) -> InAppNotification:
    entry = InAppNotification(
        user_id=user.id, kind=kind, message=message,
        entity_type=entity_type, entity_id=entity_id,
    )
    db.add(entry)
    return entry


def dept_head_for(db: Session, department_id: int | None) -> User | None:
    if department_id is None:
        return None
    return (
        db.query(User)
        .join(User.role)
        .filter(
            User.department_id == department_id,
            User.role.has(code=RoleCode.DEPT_HEAD.value),
            User.is_active.is_(True),
        )
        .first()
    )


def notify_late_edit(
    db: Session, group: StudyGroup, editor: User, date: datetime.date, hours_late: float,
) -> None:
    """Куратор отредактировал день больше чем через 48 часов после него —
    зав. отделением должен об этом узнать (обновление 1.1). Канал —
    колокольчик в интерфейсе."""
    dept_head = dept_head_for(db, group.department_id)
    if dept_head is None or dept_head.id == editor.id:
        return
    notify(
        db, dept_head, "late_edit",
        f"{editor.full_name} отредактировал(а) посещение группы {group.code} за "
        f"{date.strftime('%d.%m.%Y')} — спустя {int(hours_late)} ч. после дня.",
        entity_type="study_group_day", entity_id=f"{group.id}:{date.isoformat()}",
    )


def purge_old_read(db: Session, user_id: int, keep_days: int = 90) -> int:
    """Удаляет у пользователя уведомления, прочитанные больше keep_days назад —
    раньше этим занималось ночное задание планировщика, которого больше нет.
    Непрочитанные не трогаем, сколько бы им ни было."""
    cutoff = utcnow() - datetime.timedelta(days=keep_days)
    return (
        db.query(InAppNotification)
        .filter(
            InAppNotification.user_id == user_id,
            InAppNotification.read_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
