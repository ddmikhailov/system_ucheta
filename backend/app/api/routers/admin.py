import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_management, require_reference_editor, scope_department_id
from app.db.session import get_db
from app.models import (
    AcademicCalendarDay,
    AssignmentRole,
    CuratorAssignment,
    Department,
    DayType,
    GroupCalendarOverride,
    MarkCode,
    Role,
    RoleCode,
    Student,
    StudentStatus,
    StudyGroup,
    User,
)
from app.core.password_policy import validate_password_strength
from app.core.security import hash_password
from app.schemas.admin import (
    CalendarDayUpsert,
    CuratorAssignmentCreate,
    DeleteResult,
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    GroupCalendarOverrideRead,
    GroupCalendarOverrideUpsert,
    MarkCodeRead,
    MarkCodeUpdate,
    SetPasswordRequest,
    SetPasswordResponse,
    StudentCreate,
    StudentRead,
    StudentUpdate,
    StudentUpdateStatus,
    StudyGroupCreate,
    StudyGroupRead,
    StudyGroupUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
    UserUpdateLeadershipDigest,
)
from app.services.audit_service import log_action
from app.services.password_service import generate_temporary_password

router = APIRouter(prefix="/admin", tags=["admin"])


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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Отделение с таким названием уже существует")
    db.refresh(dept)
    return dept


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentRead,
    dependencies=[Depends(require_admin)],
)
def update_department(department_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db)):
    dept = db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отделение не найдено")
    if payload.name is not None:
        dept.name = payload.name
    if payload.is_active is not None:
        dept.is_active = payload.is_active
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Отделение с таким названием уже существует")
    db.refresh(dept)
    return dept


def _group_read(g: StudyGroup, today: datetime.date | None = None) -> StudyGroupRead:
    today = today or datetime.date.today()
    # Архивный куратор не должен продолжать числиться куратором группы (см.
    # TODO.md 3) — иначе группа не попадает в «Вакантные», хотя ей на самом
    # деле некому заниматься.
    curator_assignment = next(
        (
            a for a in g.curator_assignments
            if a.is_active_on(today) and a.role_type.value == "curator" and a.user.is_active
        ),
        None,
    )
    return StudyGroupRead(
        id=g.id, code=g.code, course=g.course, department_id=g.department_id,
        study_form=g.study_form, is_active=g.is_active,
        curator_name=curator_assignment.user.full_name if curator_assignment else None,
        curator_assignment_id=curator_assignment.id if curator_assignment else None,
    )


def _assert_can_manage_group(user: User, group: StudyGroup) -> None:
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD and group.department_id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")


@router.get("/groups", response_model=list[StudyGroupRead])
def list_groups(
    department_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    today = datetime.date.today()
    scope = scope_department_id(user, department_id)
    q = db.query(StudyGroup)
    if scope is not None:
        q = q.filter(StudyGroup.department_id == scope)
    groups = q.order_by(StudyGroup.course, StudyGroup.code).all()
    return [_group_read(g, today) for g in groups]


@router.post(
    "/groups", response_model=StudyGroupRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_group(payload: StudyGroupCreate, db: Session = Depends(get_db)):
    group = StudyGroup(**payload.model_dump())
    db.add(group)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Группа с таким кодом уже существует")
    db.refresh(group)
    return _group_read(group)


@router.patch("/groups/{group_id}", response_model=StudyGroupRead)
def update_group(
    group_id: int, payload: StudyGroupUpdate,
    user: User = Depends(require_management), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    _assert_can_manage_group(user, group)

    data = payload.model_dump(exclude_unset=True)
    # Перенос группы в другое отделение — только администратор по колледжу.
    if "department_id" in data and RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        data.pop("department_id")

    old_active = group.is_active
    for field, value in data.items():
        setattr(group, field, value)
    if group.is_active != old_active:
        log_action(
            db, user, "group.archive" if not group.is_active else "group.restore",
            "study_group", str(group.id),
        )
    else:
        log_action(db, user, "group.update", "study_group", str(group.id))

    db.commit()
    db.refresh(group)
    return _group_read(group)


@router.delete("/groups/{group_id}", response_model=DeleteResult)
def delete_group(
    group_id: int,
    user: User = Depends(require_management), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    _assert_can_manage_group(user, group)
    if group.is_active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Сначала переведите группу в архив (снимите «активна») — удалить можно только из архива",
        )

    try:
        db.delete(group)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "У группы есть история (студенты, посещаемость, назначения кураторов) — "
            "удалить полностью нельзя, оставьте её в архиве",
        )

    log_action(db, user, "group.delete", "study_group", str(group_id))
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Группа удалена")


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


def _assert_can_manage_student(db: Session, user: User, student: Student) -> None:
    if RoleCode(user.role.code) != RoleCode.DEPT_HEAD:
        return
    group = db.get(StudyGroup, student.study_group_id)
    if group is None or group.department_id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")


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


@router.patch("/students/{student_id}/status", response_model=StudentRead)
def update_student_status(
    student_id: int, payload: StudentUpdateStatus,
    user: User = Depends(require_management), db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    _assert_can_manage_student(db, user, student)
    new_status = StudentStatus(payload.status)
    student.status = new_status
    if payload.left_at is not None:
        student.left_at = payload.left_at
    elif new_status == StudentStatus.STUDYING:
        # Возврат из академа/восстановление — дата выбытия больше не
        # актуальна, иначе студент продолжает считаться выбывшим и
        # пропадает из активного списка группы (см. TODO.md 3).
        student.left_at = None
    log_action(db, user, "student.status_change", "student", str(student.id))
    db.commit()
    db.refresh(student)
    return StudentRead(
        id=student.id, full_name=student.full_name, study_group_id=student.study_group_id,
        status=student.status, enrolled_at=student.enrolled_at, left_at=student.left_at,
    )


@router.patch("/students/{student_id}", response_model=StudentRead)
def update_student(
    student_id: int, payload: StudentUpdate,
    user: User = Depends(require_management), db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    _assert_can_manage_student(db, user, student)

    data = payload.model_dump(exclude_unset=True)
    if "study_group_id" in data and data["study_group_id"] is not None:
        target_group = db.get(StudyGroup, data["study_group_id"])
        if target_group is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Группа назначения не найдена")
        _assert_can_manage_group(user, target_group)
    if "status" in data and data["status"] is not None:
        data["status"] = StudentStatus(data["status"])

    for field, value in data.items():
        setattr(student, field, value)
    log_action(db, user, "student.update", "student", str(student.id))
    db.commit()
    db.refresh(student)
    return StudentRead(
        id=student.id, full_name=student.full_name, study_group_id=student.study_group_id,
        status=student.status, enrolled_at=student.enrolled_at, left_at=student.left_at,
    )


@router.delete("/students/{student_id}", response_model=DeleteResult)
def delete_student(
    student_id: int,
    user: User = Depends(require_management), db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    _assert_can_manage_student(db, user, student)
    if student.status == StudentStatus.STUDYING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Сначала переведите студента в академ. отпуск или отчислите — удалить можно только архивного",
        )

    try:
        db.delete(student)
        db.flush()
    except IntegrityError:
        db.rollback()
        # Есть отметки посещаемости — вместо удаления обезличиваем, чтобы не
        # потерять статистику и историю группы (обновление 1.1: удаление не
        # должно ломать базу и терять уже собранные данные).
        student.last_name = "Удалённый"
        student.first_name = "студент"
        student.middle_name = None
        log_action(db, user, "student.anonymize", "student", str(student_id))
        db.commit()
        return DeleteResult(
            deleted=False, anonymized=True,
            detail="У студента есть история посещаемости — данные обезличены, запись оставлена в архиве",
        )

    log_action(db, user, "student.delete", "student", str(student_id))
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Студент удалён")


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
    group = db.get(StudyGroup, payload.study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    curator = db.get(User, payload.user_id)
    if curator is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не найден")
    if not curator.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь в архиве — сначала восстановите его")
    if curator.role.code not in (RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Назначать на группу можно только куратора или заместителя")
    if payload.end_date is not None and payload.end_date < payload.start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Дата окончания раньше даты начала")

    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        if group.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        if curator.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Куратор не из вашего отделения")

    role_type = AssignmentRole(payload.role_type)
    # Новое назначение на ту же роль (куратор/заместитель) в этой группе
    # автоматически завершает предыдущее активное — иначе на группе
    # оказывается два "текущих" куратора одновременно (см. TODO.md 3).
    previous_active = (
        db.query(CuratorAssignment)
        .filter(
            CuratorAssignment.study_group_id == payload.study_group_id,
            CuratorAssignment.role_type == role_type,
        )
        .filter((CuratorAssignment.end_date.is_(None)) | (CuratorAssignment.end_date >= payload.start_date))
        .all()
    )
    for prev in previous_active:
        prev.end_date = payload.start_date - datetime.timedelta(days=1)

    assignment = CuratorAssignment(
        study_group_id=payload.study_group_id, user_id=payload.user_id,
        role_type=role_type, start_date=payload.start_date, end_date=payload.end_date,
    )
    db.add(assignment)
    log_action(
        db, user, "curator_assignment.create", "curator_assignment",
        f"{payload.study_group_id}:{payload.user_id}",
    )
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id}


@router.post("/curator-assignments/{assignment_id}/end")
def end_curator_assignment(
    assignment_id: int,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    """Снять куратора/заместителя с группы — назначение не удаляется, а
    завершается датой, чтобы история «кто вёл группу когда» не терялась."""
    assignment = db.get(CuratorAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Назначение не найдено")
    _assert_can_manage_group(user, assignment.study_group)

    today = datetime.date.today()
    if assignment.end_date is None or assignment.end_date > today:
        assignment.end_date = today
    log_action(db, user, "curator_assignment.end", "curator_assignment", str(assignment.id))
    db.commit()
    return {"id": assignment.id, "end_date": assignment.end_date}


def _user_read(u: User) -> UserRead:
    return UserRead(
        id=u.id, username=u.username, full_name=u.full_name, role=u.role.code,
        display_title=u.display_title,
        department_id=u.department_id, is_active=u.is_active,
        telegram_linked=u.telegram_chat_id is not None,
        has_password=u.password_hash is not None,
        must_change_password=u.must_change_password,
        is_locked=u.is_locked,
        receives_leadership_digest=u.receives_leadership_digest,
    )


# Права на управление учётками (пароль/логин/ФИО/архив/удаление) и на смену
# ролей — см. TODO.md 1.2/1.3/1.5. Правило:
#   - admin — управляет кем угодно, назначает любую роль;
#   - tutor — как admin, но не может трогать учётки admin/tutor (иначе один
#     тьютор мог бы захватить учётку другого тьютора или администратора) и
#     не может менять роли вообще;
#   - dept_head — только curator/deputy_curator своего отделения, и может
#     назначать только роли curator/deputy_curator/dept_head (не может
#     повысить кого-то до admin/tutor/edu_department или тронуть чужого
#     dept_head/admin/tutor/edu_department, даже в своём отделении);
#   - edu_department — не управляет учётками вообще (раньше могло сбросить
#     пароль администратору — TODO.md 1.2).
_ELEVATED_ROLES = {RoleCode.ADMIN.value, RoleCode.TUTOR.value}
_DEPT_HEAD_MANAGEABLE_ROLES = {RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value}
_DEPT_HEAD_ASSIGNABLE_ROLES = {RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value, RoleCode.DEPT_HEAD.value}
# Роли, которым обязательно нужно отделение, и роли, которым оно не нужно
# (см. TODO.md 1.4: без этого зав. отделением/куратор без отделения получает
# фактически доступ ко всему колледжу, т.к. фильтры по department_id=None
# просто не применяются).
_DEPARTMENT_REQUIRED_ROLES = {RoleCode.DEPT_HEAD.value, RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value}
_DEPARTMENT_FORBIDDEN_ROLES = {RoleCode.ADMIN.value, RoleCode.TUTOR.value, RoleCode.EDU_DEPARTMENT.value}


def _assert_can_manage_user(admin: User, target: User) -> None:
    if target.id == admin.id:
        return
    admin_role = RoleCode(admin.role.code)
    if admin_role == RoleCode.ADMIN:
        return
    if admin_role == RoleCode.TUTOR:
        if target.role.code in _ELEVATED_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Только администратор может управлять учётками администратора/тьютора"
            )
        return
    if admin_role == RoleCode.DEPT_HEAD:
        if admin.department_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "У вас не задано отделение — обратитесь к администратору")
        if target.department_id != admin.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь не относится к вашему отделению")
        if target.role.code not in _DEPT_HEAD_MANAGEABLE_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Зав. отделением может управлять только кураторами и заместителями"
            )
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для управления пользователями")


def _assert_can_assign_role(admin: User, new_role_code: str) -> None:
    admin_role = RoleCode(admin.role.code)
    if admin_role == RoleCode.ADMIN:
        return
    if admin_role == RoleCode.DEPT_HEAD and new_role_code in _DEPT_HEAD_ASSIGNABLE_ROLES:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для назначения этой роли")


def _resolve_department_for_role(role_code: str, requested_department_id: int | None) -> int | None:
    """Отделение проставляется только там, где оно осмысленно (см. TODO.md
    1.3/1.4): у admin/tutor/edu_department его вообще не должно быть — форма
    создания пользователя раньше подставляла отделение всем без разбора."""
    if role_code in _DEPARTMENT_FORBIDDEN_ROLES:
        return None
    if role_code in _DEPARTMENT_REQUIRED_ROLES and requested_department_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Для этой роли нужно указать отделение")
    return requested_department_id


@router.get("/users", response_model=list[UserRead])
def list_users(user: User = Depends(require_management), db: Session = Depends(get_db)):
    q = db.query(User)
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        scope = scope_department_id(user, None)
        q = q.filter(User.department_id == scope)
    users = q.all()
    return [_user_read(u) for u in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.code == payload.role).one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестная роль")
    if payload.role in _ELEVATED_ROLES and RoleCode(admin.role.code) != RoleCode.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Только администратор может создавать учётки администратора/тьютора"
        )
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Логин уже занят")
    department_id = _resolve_department_for_role(payload.role, payload.department_id)

    user = User(
        username=payload.username, full_name=payload.full_name,
        role_id=role.id, department_id=department_id, password_hash=None,
        display_title=payload.display_title,
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

    if payload.role is not None and payload.role != target.role.code:
        if target.id == admin.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя менять свою собственную роль")
        _assert_can_assign_role(admin, payload.role)
        new_role = db.query(Role).filter(Role.code == payload.role).one_or_none()
        if new_role is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестная роль")
        old_role = target.role.code
        target.role_id = new_role.id
        target.token_version += 1
        # Отделение приводим в соответствие новой роли — иначе, например,
        # только что назначенный admin/tutor остаётся числиться в старом
        # отделении, что путает scope-проверки (см. TODO.md 1.4).
        target.department_id = _resolve_department_for_role(
            payload.role, payload.department_id if payload.department_id is not None else target.department_id
        )
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
        and RoleCode(admin.role.code) != RoleCode.DEPT_HEAD
    ):
        target.department_id = _resolve_department_for_role(target.role.code, payload.department_id)

    if payload.is_active is not None:
        if target.id == admin.id and not payload.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя заблокировать самого себя")
        if target.is_active != payload.is_active:
            target.is_active = payload.is_active
            target.token_version += 1
            if not payload.is_active:
                # Архивный пользователь не должен продолжать действовать
                # через бота (сдавать день, получать напоминания/дайджесты)
                # и оставаться "текущим" куратором группы (см. TODO.md 2/3).
                target.telegram_chat_id = None
                target.telegram_linked_at = None
                today = datetime.date.today()
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
    _assert_can_manage_user(admin, target)
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
        target.telegram_chat_id = None
        target.telegram_linked_at = None
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
    _assert_can_manage_user(admin, target)

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
    _assert_can_manage_user(admin, target)

    target.failed_login_attempts = 0
    target.locked_until = None
    log_action(db, admin, "user.unlock", "user", str(target.id))
    db.commit()
    db.refresh(target)
    return _user_read(target)


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


@router.get(
    "/calendar/group-overrides", response_model=list[GroupCalendarOverrideRead],
    dependencies=[Depends(require_management)],
)
def list_group_calendar_overrides(
    study_group_id: int, date_from: datetime.date, date_to: datetime.date, db: Session = Depends(get_db),
):
    rows = (
        db.query(GroupCalendarOverride)
        .filter(
            GroupCalendarOverride.study_group_id == study_group_id,
            GroupCalendarOverride.date >= date_from,
            GroupCalendarOverride.date <= date_to,
        )
        .all()
    )
    return [{"study_group_id": r.study_group_id, "date": r.date, "day_type": r.day_type} for r in rows]


@router.put(
    "/calendar/group-overrides", response_model=GroupCalendarOverrideRead,
    dependencies=[Depends(require_reference_editor)],
)
def upsert_group_calendar_override(
    payload: GroupCalendarOverrideUpsert, user: User = Depends(require_reference_editor), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, payload.study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    key = (payload.study_group_id, payload.date)
    row = db.get(GroupCalendarOverride, key)
    old_value = row.day_type if row else None
    if row is None:
        row = GroupCalendarOverride(
            study_group_id=payload.study_group_id, date=payload.date, day_type=DayType(payload.day_type)
        )
        db.add(row)
    else:
        row.day_type = DayType(payload.day_type)
    log_action(
        db, user, "calendar.group_override.upsert", "academic_calendar_group_override",
        f"{payload.study_group_id}:{payload.date}", old_value=old_value, new_value=payload.day_type,
    )
    db.commit()
    return {"study_group_id": row.study_group_id, "date": row.date, "day_type": row.day_type}


@router.delete(
    "/calendar/group-overrides", response_model=DeleteResult,
    dependencies=[Depends(require_reference_editor)],
)
def delete_group_calendar_override(
    study_group_id: int, date: datetime.date,
    user: User = Depends(require_reference_editor), db: Session = Depends(get_db),
):
    row = db.get(GroupCalendarOverride, (study_group_id, date))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Переопределение не найдено")
    db.delete(row)
    log_action(
        db, user, "calendar.group_override.delete", "academic_calendar_group_override",
        f"{study_group_id}:{date}", old_value=row.day_type,
    )
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Переопределение удалено, действует общий календарь")


@router.delete("/calendar/{date}", response_model=DeleteResult, dependencies=[Depends(require_reference_editor)])
def delete_calendar_day(
    date: datetime.date, user: User = Depends(require_reference_editor), db: Session = Depends(get_db),
):
    """Раньше "вернуть" исключение можно было только выставив «Учебный
    день» — для субботы это делало её учебной для всех курсов, а не просто
    убирало исключение (см. TODO.md 3). Зарегистрирован после
    /calendar/group-overrides: иначе DELETE .../group-overrides сам попадал
    бы сюда как date="group-overrides" (422 на разборе даты)."""
    row = db.get(AcademicCalendarDay, date)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Исключение не найдено")
    db.delete(row)
    log_action(db, user, "calendar.delete", "academic_calendar", str(date), old_value=row.day_type)
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Исключение удалено, действует правило по умолчанию")
