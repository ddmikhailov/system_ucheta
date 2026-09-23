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
        .filter(User.department_id == department_id, User.role.has(code=RoleCode.DEPT_HEAD.value))
        .first()
    )


def notify_late_edit(
    db: Session, group: StudyGroup, editor: User, date: datetime.date, hours_late: float,
) -> None:
    """Куратор отредактировал день больше чем через 48 часов после него —
    зав. отделением должен об этом узнать (обновление 1.1). Единственный
    канал сейчас — колокольчик в интерфейсе: Telegram скрыт."""
    dept_head = dept_head_for(db, group.department_id)
    if dept_head is None or dept_head.id == editor.id:
        return
    notify(
        db, dept_head, "late_edit",
        f"{editor.full_name} отредактировал(а) посещение группы {group.code} за "
        f"{date.strftime('%d.%m.%Y')} — спустя {int(hours_late)} ч. после дня.",
        entity_type="study_group_day", entity_id=f"{group.id}:{date.isoformat()}",
    )
