from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.time import utcnow
from app.db.session import get_db
from app.models import InAppNotification, User
from app.services import audit_service, in_app_notification_service, meal_service, task_schedule, task_service
from app.schemas.notifications import NotificationRead, UnreadCountResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Больше колокольчик не показывает; без верхней границы ?limit=100000 выгружал бы всё накопленное разом.
MAX_LIMIT = 200


def _unread_response(db: Session, user: User) -> UnreadCountResponse:
    total, manage = in_app_notification_service.unread_counts(db, user)
    return UnreadCountResponse(unread=total, unread_work=total - manage, unread_manage=manage)


def _task_reminders(db: Session, user: User) -> None:
    """Сроки задач проверяем при открытии платформы. Раньше это делал каждый GET колокольчика, то есть чтение
    писало в базу раз в минуту из каждой вкладки; теперь — только POST /notifications/check (интерфейс зовёт его
    при входе и раз в несколько минут, пока вкладка видна)."""
    # Сначала периодические задачи: их «новая задача» тоже попадёт в этот же опрос.
    task_schedule.run_due_templates(db)
    meal_service.ensure_weekly_task(db)
    # Срок хранения журнала действий (не больше года) — раз в сутки.
    audit_service.purge_expired_daily(db)
    if task_service.generate_reminders(db, user):
        db.commit()


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    limit: int = 50,
    category: Literal["work", "manage"] | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InAppNotification).filter(InAppNotification.user_id == user.id)
    if category is not None:
        q = q.filter(in_app_notification_service.in_category(category))
    rows = q.order_by(InAppNotification.created_at.desc()).limit(max(1, min(limit, MAX_LIMIT))).all()
    return rows


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Только чтение. Интерфейс берёт это число из /my-day/counters; ручка оставлена для совместимости."""
    return _unread_response(db, user)


@router.post("/check", response_model=UnreadCountResponse)
def check(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Периодические задачи и напоминания о сроках («при открытии платформы»): шаблоны, задача по питанию,
    напоминания пользователю. Сами функции не чаще раза в 10 минут ходят в базу, поэтому частый вызов безопасен."""
    _task_reminders(db, user)
    return _unread_response(db, user)


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
        q = q.filter(in_app_notification_service.in_category(category))
    q.update({"read_at": utcnow()}, synchronize_session=False)
    in_app_notification_service.purge_old_read(db, user.id)
    db.commit()
    return {"ok": True}
