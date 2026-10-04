"""Пользователи: список, создание, правка, пароль, разблокировка, архив/удаление."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_dept_editor, require_management, scope_department_id
from app.core import policies
from app.core.roles import is_department_scoped
from app.core.time import today_local
from app.db.session import get_db
from app.models import CuratorAssignment, Role, RoleCode, User
from app.core.password_policy import validate_password_strength
from app.core.security import hash_password
from app.schemas.admin import (
    DeleteResult,
    SetPasswordRequest,
    SetPasswordResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.audit_service import log_action, redact_audit_history
from app.services.password_service import generate_temporary_password

router = APIRouter()


def _user_read(u: User) -> UserRead:
    return UserRead(
        id=u.id, username=u.username, full_name=u.full_name, role=u.role.code,
        display_title=u.display_title,
        department_id=u.department_id, is_active=u.is_active,
        has_password=u.password_hash is not None,
        must_change_password=u.must_change_password,
        is_locked=u.is_locked,
    )




@router.get("/users", response_model=list[UserRead])
def list_users(user: User = Depends(require_management), db: Session = Depends(get_db)):
    q = db.query(User)
    if is_department_scoped(user):
        scope = scope_department_id(user, None)
        q = q.filter(User.department_id == scope)
    users = q.all()
    return [_user_read(u) for u in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: User = Depends(require_dept_editor), db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.code == payload.role).one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестная роль")
    if payload.role in policies.ELEVATED_ROLES and RoleCode(admin.role.code) != RoleCode.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Только администратор может создавать учётки администратора/тьютора"
        )
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Логин уже занят")
    if is_department_scoped(admin):
        # Зав. отделением и тьютор заводят людей только в своё отделение и только допустимые роли.
        policies.assert_can_assign_role(admin, payload.role)
        payload.department_id = scope_department_id(admin, None)
    department_id = policies.resolve_department_for_role(payload.role, payload.department_id)

    user = User(
        username=payload.username, full_name=payload.full_name,
        role_id=role.id, department_id=department_id, password_hash=None,
        display_title=payload.display_title,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, admin, "user.create", "user", str(user.id), new_value=user.username)
    db.commit()
    return _user_read(user)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int, payload: UserUpdate,
    admin: User = Depends(require_management), db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    policies.assert_can_manage_user(admin, target)

    if payload.role is not None and payload.role != target.role.code:
        if target.id == admin.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя менять свою собственную роль")
        policies.assert_can_assign_role(admin, payload.role)
        new_role = db.query(Role).filter(Role.code == payload.role).one_or_none()
        if new_role is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестная роль")
        old_role = target.role.code
        target.role_id = new_role.id
        target.token_version += 1
        # Отделение приводим в соответствие новой роли — иначе, например,
        # только что назначенный admin/tutor остаётся числиться в старом
        # отделении, что путает scope-проверки (см. TODO.md 1.4).
        # Зав. отделением не может переносить людей между отделениями через
        # смену роли — отделение остаётся тем, что уже у цели (= его собственное).
        requested_department_id = (
            target.department_id
            if is_department_scoped(admin) or payload.department_id is None
            else payload.department_id
        )
        target.department_id = policies.resolve_department_for_role(payload.role, requested_department_id)
        log_action(db, admin, "user.role_change", "user", str(target.id), old_value=old_role, new_value=payload.role)

    if payload.username is not None and payload.username != target.username:
        if db.query(User).filter(User.username == payload.username, User.id != target.id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Логин уже занят")
        old_username = target.username
        target.username = payload.username
        log_action(db, admin, "user.username_change", "user", str(target.id), old_value=old_username, new_value=payload.username)

    if payload.full_name is not None:
        target.full_name = payload.full_name

    if payload.display_title is not None:
        target.display_title = payload.display_title or None

    if (
        payload.department_id is not None
        and (payload.role is None or payload.role == target.role.code)
        and not is_department_scoped(admin)
    ):
        target.department_id = policies.resolve_department_for_role(target.role.code, payload.department_id)

    if payload.is_active is not None:
        if target.id == admin.id and not payload.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя заблокировать самого себя")
        if target.is_active != payload.is_active:
            target.is_active = payload.is_active
            target.token_version += 1
            if not payload.is_active:
                # Архивный пользователь не должен оставаться "текущим"
                # куратором группы (см. TODO.md 2/3).
                today = today_local()
                for assignment in (
                    db.query(CuratorAssignment)
                    .filter(CuratorAssignment.user_id == target.id)
                    .filter((CuratorAssignment.end_date.is_(None)) | (CuratorAssignment.end_date >= today))
                    .all()
                ):
                    assignment.end_date = today
            log_action(
                db, admin, "user.archive" if not payload.is_active else "user.restore",
                "user", str(target.id),
            )

    db.commit()
    db.refresh(target)
    return _user_read(target)


@router.delete("/users/{user_id}", response_model=DeleteResult)
def delete_user(
    user_id: int,
    admin: User = Depends(require_management), db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    policies.assert_can_manage_user(admin, target)
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя удалить самого себя")
    if target.is_active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Сначала заблокируйте пользователя (снимите «активен») — удалить можно только из архива",
        )

    try:
        db.delete(target)
        db.flush()
    except IntegrityError:
        db.rollback()
        # Есть история (отметки, сдачи дня, назначения на группы, журнал
        # действий) — вместо удаления обезличиваем: имя и логин заменяются
        # на плейсхолдер, но статистика и записи, которые он оставил,
        # никуда не пропадают (обновление 1.1).
        placeholder = f"deleted_{target.id}"
        target.username = placeholder
        target.full_name = "Удалённый пользователь"
        target.password_hash = None
        redact_audit_history(db, "user", str(user_id))
        log_action(db, admin, "user.anonymize", "user", str(user_id))
        db.commit()
        return DeleteResult(
            deleted=False, anonymized=True,
            detail="У пользователя есть история действий — данные обезличены, запись оставлена в архиве",
        )

    log_action(db, admin, "user.delete", "user", str(user_id))
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Пользователь удалён")


@router.post("/users/{user_id}/set-password", response_model=SetPasswordResponse)
def set_password(
    user_id: int, payload: SetPasswordRequest,
    admin: User = Depends(require_management), db: Session = Depends(get_db),
):
    """Администратор/зав. отделением выдаёт временный пароль напрямую —
    без одноразовой ссылки. При следующем входе пользователь обязан
    задать свой пароль (см. POST /auth/change-password)."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    policies.assert_can_manage_user(admin, target)

    password = payload.password or generate_temporary_password()
    if payload.password is not None:
        try:
            validate_password_strength(password, target.username)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    target.password_hash = hash_password(password)
    target.must_change_password = True
    target.token_version += 1
    # Заодно снимаем блокировку — типовой сценарий обращения «не могу войти».
    target.failed_login_attempts = 0
    target.locked_until = None

    log_action(db, admin, "user.password_set", "user", str(target.id))
    db.commit()

    return SetPasswordResponse(username=target.username, password=password)


@router.post("/users/{user_id}/unlock", response_model=UserRead)
def unlock_user(
    user_id: int,
    admin: User = Depends(require_management), db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    policies.assert_can_manage_user(admin, target)

    target.failed_login_attempts = 0
    target.locked_until = None
    log_action(db, admin, "user.unlock", "user", str(target.id))
    db.commit()
    db.refresh(target)
    return _user_read(target)
