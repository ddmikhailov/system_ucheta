import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_management, require_reference_editor
from app.db.session import get_db
from app.models import (
    AcademicCalendarDay,
    AssignmentRole,
    CuratorAssignment,
    Department,
    DayType,
    MarkCode,
    Role,
    RoleCode,
    Student,
    StudentStatus,
    StudyGroup,
    User,
)
from app.core.security import hash_password
from app.schemas.admin import (
    CalendarDayUpsert,
    CuratorAssignmentCreate,
    DepartmentCreate,
    DepartmentRead,
    InvitationRead,
    MarkCodeRead,
    MarkCodeUpdate,
    SetPasswordRequest,
    SetPasswordResponse,
    StudentCreate,
    StudentRead,
    StudentUpdateStatus,
    StudyGroupCreate,
    StudyGroupRead,
    UserCreate,
    UserRead,
    UserUpdate,
    UserUpdateLeadershipDigest,
)
from app.services.audit_service import log_action
from app.services.invitation_service import create_invitation
from app.services.password_service import generate_temporary_password

router = APIRouter(prefix="/admin", tags=["admin"])


def _scope_department_id(user: User, requested: int | None) -> int | None:
    """Зав. отделением всегда ограничен своим отделением, остальные — по запросу."""
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        return user.department_id
    return requested


@router.get("/departments", response_model=list[DepartmentRead], dependencies=[Depends(require_management)])
def list_departments(db: Session = Depends(get_db)):
    return db.query(Department).all()


@router.post(
    "/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    dept = Department(name=payload.name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get("/groups", response_model=list[StudyGroupRead])
def list_groups(
    department_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    today = datetime.date.today()
    scope = _scope_department_id(user, department_id)
    q = db.query(StudyGroup)
    if scope is not None:
        q = q.filter(StudyGroup.department_id == scope)
    groups = q.order_by(StudyGroup.course, StudyGroup.code).all()

    result = []
    for g in groups:
        curator = next(
            (a.user.full_name for a in g.curator_assignments if a.is_active_on(today) and a.role_type.value == "curator"),
            None,
        )
        result.append(
            StudyGroupRead(
                id=g.id, code=g.code, course=g.course, department_id=g.department_id,
                study_form=g.study_form, is_active=g.is_active, curator_name=curator,
            )
        )
    return result


@router.post(
    "/groups", response_model=StudyGroupRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_group(payload: StudyGroupCreate, db: Session = Depends(get_db)):
    group = StudyGroup(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return StudyGroupRead(
        id=group.id, code=group.code, course=group.course, department_id=group.department_id,
        study_form=group.study_form, is_active=group.is_active, curator_name=None,
    )


@router.get("/students", response_model=list[StudentRead])
def list_students(
    study_group_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    q = db.query(Student)
    if study_group_id is not None:
        q = q.filter(Student.study_group_id == study_group_id)
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        q = q.join(StudyGroup, StudyGroup.id == Student.study_group_id).filter(
            StudyGroup.department_id == user.department_id
        )
    students = q.order_by(Student.last_name, Student.first_name).all()
    return [
        StudentRead(
            id=s.id, full_name=s.full_name, study_group_id=s.study_group_id,
            status=s.status, enrolled_at=s.enrolled_at, left_at=s.left_at,
        )
        for s in students
    ]


@router.post(
    "/students", response_model=StudentRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return StudentRead(
        id=student.id, full_name=student.full_name, study_group_id=student.study_group_id,
        status=student.status, enrolled_at=student.enrolled_at, left_at=student.left_at,
    )


@router.patch(
    "/students/{student_id}/status", response_model=StudentRead,
    dependencies=[Depends(require_management)],
)
def update_student_status(student_id: int, payload: StudentUpdateStatus, db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    student.status = StudentStatus(payload.status)
    if payload.left_at is not None:
        student.left_at = payload.left_at
    db.commit()
    db.refresh(student)
    return StudentRead(
        id=student.id, full_name=student.full_name, study_group_id=student.study_group_id,
        status=student.status, enrolled_at=student.enrolled_at, left_at=student.left_at,
    )


@router.get("/mark-codes", response_model=list[MarkCodeRead], dependencies=[Depends(require_management)])
def list_mark_codes(db: Session = Depends(get_db)):
    return db.query(MarkCode).order_by(MarkCode.sort_order).all()


@router.patch(
    "/mark-codes/{mark_code_id}", response_model=MarkCodeRead,
    dependencies=[Depends(require_reference_editor)],
)
def update_mark_code(mark_code_id: int, payload: MarkCodeUpdate, db: Session = Depends(get_db)):
    mark_code = db.get(MarkCode, mark_code_id)
    if mark_code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Код не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mark_code, field, value)
    db.commit()
    db.refresh(mark_code)
    return mark_code


@router.post("/curator-assignments", status_code=status.HTTP_201_CREATED)
def create_curator_assignment(
    payload: CuratorAssignmentCreate,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        group = db.get(StudyGroup, payload.study_group_id)
        if group is None or group.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        curator = db.get(User, payload.user_id)
        if curator is None or curator.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Куратор не из вашего отделения")

    data = payload.model_dump()
    data["role_type"] = AssignmentRole(data["role_type"])
    assignment = CuratorAssignment(**data)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id}


def _user_read(u: User) -> UserRead:
    return UserRead(
        id=u.id, username=u.username, full_name=u.full_name, role=u.role.code,
        department_id=u.department_id, is_active=u.is_active,
        telegram_linked=u.telegram_chat_id is not None,
        has_password=u.password_hash is not None,
        must_change_password=u.must_change_password,
        is_locked=u.is_locked,
        receives_leadership_digest=u.receives_leadership_digest,
    )


def _assert_can_manage_user(admin: User, target: User) -> None:
    """Зав. отделением управляет логинами/паролями только внутри своего
    отделения; воспитательный отдел и администратор — без ограничений."""
    if RoleCode(admin.role.code) == RoleCode.DEPT_HEAD and target.department_id != admin.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь не относится к вашему отделению")


@router.get("/users", response_model=list[UserRead])
def list_users(user: User = Depends(require_management), db: Session = Depends(get_db)):
    q = db.query(User)
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        q = q.filter(User.department_id == user.department_id)
    users = q.all()
    return [_user_read(u) for u in users]


@router.post(
    "/users", response_model=UserRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.code == payload.role).one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестная роль")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Логин уже занят")

    user = User(
        username=payload.username, full_name=payload.full_name,
        role_id=role.id, department_id=payload.department_id, password_hash=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_read(user)


@router.patch(
    "/users/{user_id}/leadership-digest", response_model=UserRead,
    dependencies=[Depends(require_admin)],
)
def update_leadership_digest(user_id: int, payload: UserUpdateLeadershipDigest, db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    target.receives_leadership_digest = payload.receives_leadership_digest
    db.commit()
    db.refresh(target)
    return _user_read(target)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int, payload: UserUpdate,
    admin: User = Depends(require_management), db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    _assert_can_manage_user(admin, target)

    if payload.username is not None and payload.username != target.username:
        if db.query(User).filter(User.username == payload.username, User.id != target.id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Логин уже занят")
        old_username = target.username
        target.username = payload.username
        log_action(db, admin, "user.username_change", "user", str(target.id), old_value=old_username, new_value=payload.username)

    if payload.full_name is not None:
        target.full_name = payload.full_name

    if payload.department_id is not None and RoleCode(admin.role.code) != RoleCode.DEPT_HEAD:
        target.department_id = payload.department_id

    db.commit()
    db.refresh(target)
    return _user_read(target)


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
    _assert_can_manage_user(admin, target)

    password = payload.password or generate_temporary_password()
    target.password_hash = hash_password(password)
    target.must_change_password = True
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
    _assert_can_manage_user(admin, target)

    target.failed_login_attempts = 0
    target.locked_until = None
    log_action(db, admin, "user.unlock", "user", str(target.id))
    db.commit()
    db.refresh(target)
    return _user_read(target)


@router.post(
    "/users/{user_id}/invitations", response_model=InvitationRead,
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
def issue_invitation(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    # Оставлено ради обратной совместимости (принятые ранее ссылки и тесты);
    # в интерфейсе администратора этот путь больше не используется — вместо
    # него выдача временного пароля (POST /users/{id}/set-password), см.
    # обновление 1.1.
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    invitation = create_invitation(db, target, admin)
    return InvitationRead(
        token=invitation.token,
        expires_at=invitation.expires_at,
        invitation_url_path=f"/invite/{invitation.token}",
    )


@router.get("/calendar", dependencies=[Depends(require_management)])
def list_calendar(date_from: datetime.date, date_to: datetime.date, db: Session = Depends(get_db)):
    rows = (
        db.query(AcademicCalendarDay)
        .filter(AcademicCalendarDay.date >= date_from, AcademicCalendarDay.date <= date_to)
        .all()
    )
    return [{"date": r.date, "day_type": r.day_type} for r in rows]


@router.put("/calendar", dependencies=[Depends(require_reference_editor)])
def upsert_calendar_day(payload: CalendarDayUpsert, user: User = Depends(require_reference_editor), db: Session = Depends(get_db)):
    row = db.get(AcademicCalendarDay, payload.date)
    old_value = row.day_type if row else None
    if row is None:
        row = AcademicCalendarDay(date=payload.date, day_type=DayType(payload.day_type))
        db.add(row)
    else:
        row.day_type = DayType(payload.day_type)
    log_action(db, user, "calendar.upsert", "academic_calendar", str(payload.date), old_value=old_value, new_value=payload.day_type)
    db.commit()
    return {"date": row.date, "day_type": row.day_type}
