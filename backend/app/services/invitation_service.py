import datetime

from sqlalchemy.orm import Session

from app.core.security import generate_invitation_token, hash_password
from app.core.time import utcnow
from app.models import Invitation, User
from app.services.audit_service import log_action

INVITATION_TTL_DAYS = 14


def create_invitation(db: Session, target_user: User, issued_by: User) -> Invitation:
    invitation = Invitation(
        token=generate_invitation_token(),
        user_id=target_user.id,
        issued_by_user_id=issued_by.id,
        expires_at=utcnow() + datetime.timedelta(days=INVITATION_TTL_DAYS),
    )
    db.add(invitation)
    log_action(db, issued_by, "invitation.create", "user", str(target_user.id))
    db.commit()
    db.refresh(invitation)
    return invitation


def accept_invitation(db: Session, token: str, password: str) -> User:
    invitation = db.query(Invitation).filter(Invitation.token == token).one_or_none()
    if invitation is None or not invitation.is_usable:
        raise ValueError("Ссылка недействительна или срок её действия истёк")

    user = invitation.user
    user.password_hash = hash_password(password)
    invitation.used_at = utcnow()
    log_action(db, user, "invitation.accept", "user", str(user.id))
    db.commit()
    db.refresh(user)
    return user
