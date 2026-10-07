from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.password_policy import validate_password_strength
from app.core.rate_limit import check_rate_limit, client_ip, is_blocked, register_failure, reset_failures
from app.core.security import create_access_token, hash_password, verify_password
from app.core.time import today_local
from app.db.session import get_db
from app.models import CuratorAssignment, RoleCode, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeGroupInfo,
    MeResponse,
    TokenResponse,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
PRIVILEGED_ROLES = {RoleCode.ADMIN, RoleCode.EDU_DEPARTMENT, RoleCode.DEPT_HEAD, RoleCode.TUTOR}
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # По IP, а не по логину — иначе перебор паролей просто размазывается по
    # разным существующим учёткам и никогда не упирается в лимит (см.
    # TODO.md 2). Порог заметно выше, чем per-account лимит блокировки ниже,
    # чтобы не мешать обычным опечаткам нескольких разных людей из одной сети.
    ip = client_ip(request)
    if not check_rate_limit(f"login:{ip}", max_attempts=30, window_seconds=300):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток входа — попробуйте позже")

    # Блокируется не учётная запись, а связка «адрес + логин»: раньше пять
    # неверных паролей подряд закрывали вход самому владельцу на 15 минут, и
    # любой, кто знает логин, мог сделать это удалённо. Теперь подбор с одного
    # адреса упирается в лимит только для этого адреса — настоящий пользователь
    # со своего адреса входит как обычно.
    fail_key = f"{ip}:{payload.username.strip().lower()}"
    user = db.query(User).filter(User.username == payload.username).one_or_none()

    # Учётные записи с широкими правами (администрация, зав. отделением, тьютор)
    # защищены строже: адрес-подборщик останавливается быстрее и на дольше. Саму
    # учётную запись это не блокирует — владелец со своего адреса входит всегда.
    privileged = user is not None and user.role.code in PRIVILEGED_ROLES
    max_failures = settings.max_failed_login_attempts
    window = settings.lockout_minutes * 60
    if privileged:
        max_failures = settings.max_failed_login_attempts_privileged
        window *= 2
    if is_blocked(fail_key, max_failures, window):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Слишком много неудачных попыток входа — попробуйте через {window // 60} мин.",
        )

    # Пароль проверяется и для несуществующего логина (по пустышке), чтобы по
    # времени ответа нельзя было отличить «нет такого логина» от «неверный пароль».
    password_ok = verify_password(
        payload.password, user.password_hash if user and user.password_hash else _DUMMY_HASH
    ) and user is not None and user.password_hash is not None

    if not password_ok:
        failures = register_failure(fail_key, window)
        if privileged and failures == max_failures:
            # Попытка подбора пароля к привилегированной учётке — в журнал, чтобы
            # администрация видела её без чтения логов сервера.
            log_action(db, user, "auth.bruteforce_blocked", "user", str(user.id), new_value=ip)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Учётная запись отключена")

    reset_failures(fail_key)

    token = create_access_token(user.id, user.role.code, user.token_version)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
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
            .filter(User.is_active.is_(True))
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
