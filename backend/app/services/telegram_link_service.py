import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_invitation_token
from app.core.time import utcnow
from app.models import TelegramLinkToken, User
from app.services.audit_service import log_action

settings = get_settings()


def create_link_token(db: Session, user: User) -> TelegramLinkToken:
    token = TelegramLinkToken(
        token=generate_invitation_token(),
        user_id=user.id,
        expires_at=utcnow() + datetime.timedelta(minutes=settings.telegram_link_token_ttl_minutes),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def build_deep_link(token: str) -> str:
    return f"https://t.me/{settings.telegram_bot_username}?start={token}"


class LinkTokenInvalid(Exception):
    pass


class ChatAlreadyLinked(Exception):
    pass


def consume_link_token(db: Session, token_value: str, chat_id: str) -> User:
    """Вызывается ботом при получении /start <token> — привязывает chat_id к пользователю."""
    token = db.query(TelegramLinkToken).filter(TelegramLinkToken.token == token_value).one_or_none()
    if token is None or not token.is_usable:
        raise LinkTokenInvalid("Ссылка недействительна или срок её действия истёк")

    existing = db.query(User).filter(User.telegram_chat_id == chat_id).one_or_none()
    if existing is not None and existing.id != token.user_id:
        raise ChatAlreadyLinked("Этот Telegram уже привязан к другой учётной записи")

    user = token.user
    user.telegram_chat_id = chat_id
    user.telegram_linked_at = utcnow()
    token.used_at = utcnow()
    log_action(db, user, "telegram.link", "user", str(user.id))
    db.commit()
    db.refresh(user)
    return user


def unlink_telegram(db: Session, user: User) -> None:
    user.telegram_chat_id = None
    user.telegram_linked_at = None
    log_action(db, user, "telegram.unlink", "user", str(user.id))
    db.commit()
