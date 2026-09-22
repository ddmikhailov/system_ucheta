import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.time import utcnow
from app.db.session import get_db
from app.models import CuratorAssignment, Invitation, User
from app.schemas.auth import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    InvitationPreview,
    LoginRequest,
    MeGroupInfo,
    MeResponse,
    TelegramLinkResponse,
    TokenResponse,
)
from app.services.audit_service import log_action
from app.services.invitation_service import accept_invitation
from app.services.telegram_link_service import build_deep_link, create_link_token, unlink_telegram

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
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

    token = create_access_token(user.id, user.role.code)
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

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    log_action(db, user, "password.change", "user", str(user.id))
    db.commit()

    return me(user, db)


@router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, db: Session = Depends(get_db)):
    invitation = db.query(Invitation).filter(Invitation.token == token).one_or_none()
    if invitation is None or not invitation.is_usable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ссылка недействительна или срок её действия истёк")

    user = invitation.user
    assignments = db.query(CuratorAssignment).filter(CuratorAssignment.user_id == user.id).all()
    return InvitationPreview(
        full_name=user.full_name,
        role=user.role.code,
        groups=[a.study_group.code for a in assignments],
    )


@router.post("/invitations/{token}/accept", response_model=TokenResponse)
def accept_invitation_route(token: str, payload: AcceptInvitationRequest, db: Session = Depends(get_db)):
    try:
        user = accept_invitation(db, token, payload.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    token_value = create_access_token(user.id, user.role.code)
    return TokenResponse(access_token=token_value)


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
