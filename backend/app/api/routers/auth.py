import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.password_policy import validate_password_strength
from app.core.rate_limit import check_rate_limit, client_ip
from app.core.security import create_access_token, hash_password, verify_password
from app.core.time import utcnow
from app.db.session import get_db
from app.models import CuratorAssignment, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeGroupInfo,
    MeResponse,
    TelegramLinkResponse,
    TokenResponse,
)
from app.services.audit_service import log_action
from app.services.telegram_link_service import build_deep_link, create_link_token, unlink_telegram

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # По IP, а не по логину — иначе перебор паролей просто размазывается по
    # разным существующим учёткам и никогда не упирается в лимит (см.
    # TODO.md 2). Порог заметно выше, чем per-account лимит блокировки ниже,
    # чтобы не мешать обычным опечаткам нескольких разных людей из одной сети.
    ip = client_ip(request)
    if not check_rate_limit(f"login:{ip}", max_attempts=30, window_seconds=300):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток входа — попробуйте позже")

    user = db.query(User).filter(User.username == payload.username).one_or_none()

    generic_error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")

    if user is None or user.password_hash is None:
        raise generic_error

    if user.locked_until and user.locked_until > utcnow():
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Учётная запись заблокирована до {user.locked_until.isoformat()} из-за неудачных попыток входа",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.locked_until = utcnow() + datetime.timedelta(
                minutes=settings.lockout_minutes
            )
            user.failed_login_attempts = 0
        db.commit()
        raise generic_error

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Учётная запись отключена")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    token = create_access_token(user.id, user.role.code, user.token_version)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    assignments = db.query(CuratorAssignment).filter(CuratorAssignment.user_id == user.id).all()
    groups = [
        MeGroupInfo(id=a.study_group.id, code=a.study_group.code, course=a.study_group.course)
        for a in assignments
        if a.is_active_on(today)
    ]

    dept_head_name = None
    if user.department_id:
        dept_head = (
            db.query(User)
            .join(User.role)
            .filter(User.department_id == user.department_id)
            .filter(User.role.has(code="dept_head"))
            .first()
        )
        dept_head_name = dept_head.full_name if dept_head else None

    return MeResponse(
        id=user.id,
        full_name=user.full_name,
        role=user.role.code,
        display_title=user.display_title,
        department_name=user.department.name if user.department else None,
        groups=groups,
        dept_head_name=dept_head_name,
        telegram_linked=user.telegram_chat_id is not None,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password", response_model=MeResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Принудительная смена (после временного пароля от администратора) не
    # требует ввода старого пароля — пользователь и так только что вошёл
    # по нему. Добровольная смена своего пароля обязана его подтвердить.
    if not user.must_change_password:
        if payload.current_password is None or not verify_password(
            payload.current_password, user.password_hash or ""
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный текущий пароль")

    try:
        validate_password_strength(payload.new_password, user.username)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    # Отзывает все ранее выданные токены этого пользователя (см. TODO.md 2:
    # раньше украденный/оставленный где-то токен продолжал работать все 12ч
    # после смены пароля). Токен, которым выполнен сам этот запрос, тоже
    # становится недействителен — поэтому ниже выдаём новый и возвращаем
    # его же, чтобы не разлогинить только что сменившего пароль человека.
    user.token_version += 1
    log_action(db, user, "password.change", "user", str(user.id))
    db.commit()

    response = me(user, db)
    response.access_token = create_access_token(user.id, user.role.code, user.token_version)
    return response


@router.post("/telegram/link", response_model=TelegramLinkResponse)
def telegram_link(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.telegram_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram-бот не настроен")
    token = create_link_token(db, user)
    return TelegramLinkResponse(deep_link=build_deep_link(token.token), expires_at=token.expires_at.isoformat())


@router.post("/telegram/unlink", response_model=MeResponse)
def telegram_unlink(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    unlink_telegram(db, user)
    return me(user, db)
