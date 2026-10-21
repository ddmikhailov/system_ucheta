from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.time import utcnow
from app.db.session import get_db
from app.models import InAppNotification, User
from app.services import in_app_notification_service, meal_service, task_schedule, task_service
from app.schemas.notifications import NotificationRead, UnreadCountResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _in_category(category: str):
    manage = InAppNotification.kind.in_(in_app_notification_service.MANAGE_KINDS)
    return manage if category == "manage" else ~manage


def _task_reminders(db: Session, user: User) -> None:
    """Сроки задач проверяем при открытии платформы (колокольчик опрашивает эти ручки)."""
    # Сначала периодические задачи: их «новая задача» тоже попадёт в этот же опрос.
    task_schedule.run_due_templates(db)
    meal_service.ensure_weekly_task(db)
    if task_service.generate_reminders(db, user):
        db.commit()


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    limit: int = 50,
    category: Literal["work", "manage"] | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _task_reminders(db, user)
    q = db.query(InAppNotification).filter(InAppNotification.user_id == user.id)
    if category is not None:
        q = q.filter(_in_category(category))
    rows = q.order_by(InAppNotification.created_at.desc()).limit(limit).all()
    return rows


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _task_reminders(db, user)
    manage = (
        db.query(InAppNotification)
        .filter(InAppNotification.user_id == user.id, InAppNotification.read_at.is_(None), _in_category("manage"))
        .count()
    )
    total = (
        db.query(InAppNotification)
        .filter(InAppNotification.user_id == user.id, InAppNotification.read_at.is_(None))
        .count()
    )
    return UnreadCountResponse(unread=total, unread_work=total - manage, unread_manage=manage)


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notification = db.get(InAppNotification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    if notification.read_at is None:
        notification.read_at = utcnow()
    in_app_notification_service.purge_old_read(db, user.id)
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all")
def mark_all_read(
    category: Literal["work", "manage"] | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    q = db.query(InAppNotification).filter(InAppNotification.user_id == user.id, InAppNotification.read_at.is_(None))
    if category is not None:
        q = q.filter(_in_category(category))
    q.update({"read_at": utcnow()}, synchronize_session=False)
    in_app_notification_service.purge_old_read(db, user.id)
    db.commit()
    return {"ok": True}
