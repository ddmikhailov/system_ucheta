from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.time import utcnow
from app.db.session import get_db
from app.models import InAppNotification, User
from app.schemas.notifications import NotificationRead, UnreadCountResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(InAppNotification)
        .filter(InAppNotification.user_id == user.id)
        .order_by(InAppNotification.created_at.desc())
        .limit(limit)
        .all()
    )
    return rows


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = (
        db.query(InAppNotification)
        .filter(InAppNotification.user_id == user.id, InAppNotification.read_at.is_(None))
        .count()
    )
    return UnreadCountResponse(unread=count)


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notification = db.get(InAppNotification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    if notification.read_at is None:
        notification.read_at = utcnow()
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    (
        db.query(InAppNotification)
        .filter(InAppNotification.user_id == user.id, InAppNotification.read_at.is_(None))
        .update({"read_at": utcnow()})
    )
    db.commit()
    return {"ok": True}
