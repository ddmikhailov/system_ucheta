"""Отделения."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_full_access, require_viewer
from app.db.session import get_db
from app.models import Department, User
from app.schemas.admin import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/departments", response_model=list[DepartmentRead], dependencies=[Depends(require_viewer)])
def list_departments(db: Session = Depends(get_db)):
    return db.query(Department).all()


@router.post(
    "/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    payload: DepartmentCreate, user: User = Depends(require_full_access), db: Session = Depends(get_db),
):
    dept = Department(name=payload.name)
    db.add(dept)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Отделение с таким названием уже существует")
    db.refresh(dept)
    log_action(db, user, "department.create", "department", str(dept.id), new_value=dept.name)
    db.commit()
    return dept


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: int, payload: DepartmentUpdate,
    user: User = Depends(require_full_access), db: Session = Depends(get_db),
):
    dept = db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отделение не найдено")
    old_name = dept.name
    old_active = dept.is_active
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
    if dept.name != old_name:
        log_action(db, user, "department.rename", "department", str(dept.id), old_value=old_name, new_value=dept.name)
    if dept.is_active != old_active:
        log_action(
            db, user, "department.archive" if not dept.is_active else "department.restore",
            "department", str(dept.id),
        )
    db.commit()
    return dept
