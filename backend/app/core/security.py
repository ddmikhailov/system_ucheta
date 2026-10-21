from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

settings = get_settings()
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(
    subject: int, role_code: str, token_version: int, auth_time: datetime | None = None
) -> str:
    """auth_time — когда человек вводил пароль. Продлённая сессия переносит его из прежнего токена: срок
    действия не выходит за auth_time + session_max_days, сколько бы раз сессию ни продлевали."""
    now = datetime.now(timezone.utc)
    auth_time = auth_time or now
    expires = min(
        now + timedelta(minutes=settings.access_token_expire_minutes),
        auth_time + timedelta(days=settings.session_max_days),
    )
    payload = {
        "sub": str(subject),
        "role": role_code,
        # Сверяется с User.token_version в get_current_user — без этого
        # сброс пароля администратором, смена своего пароля или смена роли
        # не отзывали уже выданные токены до истечения их 12-часового срока
        # (см. TODO.md 2).
        "tv": token_version,
        "iat": now,
        "auth_time": int(auth_time.timestamp()),
        "exp": expires,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def token_auth_time(payload: dict) -> datetime:
    """Время ввода пароля; у токенов, выданных до продления сессий, его нет — берём время выдачи."""
    return datetime.fromtimestamp(payload.get("auth_time", payload["iat"]), timezone.utc)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
