"""Справочники: коды отметок и учебный календарь (общий и по группам)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_group_calendar_editor, require_management, require_reference_editor
from app.core import policies
from app.db.session import get_db
from app.models import AcademicCalendarDay, DayType, GroupCalendarOverride, MarkCode, StudyGroup, User
from app.schemas.admin import (
    CalendarDayUpsert,
    DeleteResult,
    GroupCalendarOverrideRead,
    GroupCalendarOverrideUpsert,
    MarkCodeRead,
    MarkCodeUpdate,
)
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/mark-codes", response_model=list[MarkCodeRead], dependencies=[Depends(require_management)])
def list_mark_codes(db: Session = Depends(get_db)):
    return db.query(MarkCode).order_by(MarkCode.sort_order).all()


@router.patch("/mark-codes/{mark_code_id}", response_model=MarkCodeRead)
def update_mark_code(
    mark_code_id: int, payload: MarkCodeUpdate,
    user: User = Depends(require_reference_editor), db: Session = Depends(get_db),
):
    mark_code = db.get(MarkCode, mark_code_id)
    if mark_code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Код не найден")
    # Флаги кода (counts_as_present/is_excused/...) задним числом меняют
    # смысл уже стоящих отметок во всей истории — раньше это не попадало в
    # audit_log, хотя остальные структурные правки логируются (см. TODO.md 2).
    for field, value in payload.model_dump(exclude_unset=True).items():
        old_value = getattr(mark_code, field)
        if old_value != value:
            log_action(
                db, user, "mark_code.flag_change", "mark_code", str(mark_code.id),
                old_value=f"{field}={old_value}", new_value=f"{field}={value}",
            )
        setattr(mark_code, field, value)
    db.commit()
    db.refresh(mark_code)
    return mark_code


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
    study_group_id: int, date_from: datetime.date, date_to: datetime.date,
    user: User = Depends(require_management), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    policies.assert_can_manage_group(user, group)
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
)
def upsert_group_calendar_override(
    payload: GroupCalendarOverrideUpsert, user: User = Depends(require_group_calendar_editor),
    db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, payload.study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    policies.assert_can_manage_group(user, group)
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
)
def delete_group_calendar_override(
    study_group_id: int, date: datetime.date,
    user: User = Depends(require_group_calendar_editor), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, study_group_id)
    if group is not None:
        policies.assert_can_manage_group(user, group)
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
