"""Практика группы (п. 3.1.17 положения о кураторе): периоды, база, руководители, факт получения характеристики.

Права — как у собраний и плана группы: читать — тем, кому открыт журнал группы; менять — тем, кто работает с группой.
Сводка «кто сейчас на практике» — витринам: зав. отделением и тьютор видят своё отделение, воспитательный отдел и
администратор — весь колледж (или выбранное отделение). Характеристика в платформе не хранится — только отметка и дата."""
import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user, require_viewer, scope_department_id
from app.core.time import today_local
from app.db.session import get_db
from app.models import GroupPractice, StudyGroup, User
from app.services import practice_service as svc

router = APIRouter(prefix="/practice", tags=["practice"])

Kind = Literal["educational", "production", "pre_diploma"]


class PracticeIn(BaseModel):
    kind: Kind = "production"
    date_from: datetime.date
    date_to: datetime.date
    base: str | None = Field(default=None, max_length=255)
    college_supervisor: str | None = Field(default=None, max_length=255)
    base_supervisor: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    review_received: bool = False
    review_received_on: datetime.date | None = None
    note: str | None = Field(default=None, max_length=3000)


class PracticeRead(BaseModel):
    id: int
    study_group_id: int
    kind: str
    kind_name: str
    date_from: datetime.date
    date_to: datetime.date
    base: str | None
    college_supervisor: str | None
    base_supervisor: str | None
    phone: str | None
    review_received: bool
    review_received_on: datetime.date | None
    note: str | None
    state: str | None  # active / soon / no_review — как в сводке; None — прошла с характеристикой или ещё не скоро
    replaced_marks: int = 0  # сколько уже стоявших отметок заменила практика (при сохранении)


class GroupPracticesRead(BaseModel):
    group_id: int
    can_edit: bool
    practices: list[PracticeRead]


class CurrentPracticeRow(BaseModel):
    id: int
    study_group_id: int
    group_code: str
    course: int
    department: str
    kind_name: str
    date_from: datetime.date
    date_to: datetime.date
    base: str | None
    college_supervisor: str | None
    base_supervisor: str | None
    phone: str | None
    review_received: bool
    state: str  # active / soon / no_review


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _read(p: GroupPractice, today: datetime.date, replaced: int = 0) -> PracticeRead:
    return PracticeRead(
        id=p.id, study_group_id=p.study_group_id, kind=p.kind, kind_name=svc.KINDS.get(p.kind, p.kind),
        date_from=p.date_from, date_to=p.date_to, base=p.base, college_supervisor=p.college_supervisor,
        base_supervisor=p.base_supervisor, phone=p.phone, review_received=p.review_received,
        review_received_on=p.review_received_on, note=p.note, state=svc.state_of(p, today), replaced_marks=replaced,
    )


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _practice(db: Session, practice_id: int) -> GroupPractice:
    practice = db.get(GroupPractice, practice_id)
    if practice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Практика не найдена")
    return practice


def _apply(practice: GroupPractice, payload: PracticeIn, today: datetime.date) -> None:
    try:
        svc.validate_dates(payload.date_from, payload.date_to)
    except svc.PracticeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    practice.kind = payload.kind
    practice.date_from = payload.date_from
    practice.date_to = payload.date_to
    practice.base = _clean(payload.base)
    practice.college_supervisor = _clean(payload.college_supervisor)
    practice.base_supervisor = _clean(payload.base_supervisor)
    practice.phone = _clean(payload.phone)
    practice.review_received = payload.review_received
    practice.review_received_on = (payload.review_received_on or today) if payload.review_received else None
    practice.note = _clean(payload.note)


def _save(db: Session, user: User, practice: GroupPractice, action: str) -> PracticeRead:
    """Сохранить практику и расставить отметки. Ответ собирается до commit()."""
    today = today_local()
    replaced = svc.count_replaced_marks(db, practice.study_group_id, practice.date_from, practice.date_to)
    try:
        svc.sync(db, practice, user)
    except svc.PracticeError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    svc.audit(db, user, action, practice)
    result = _read(practice, today, replaced)
    db.commit()
    return result


@router.get("/current", response_model=list[CurrentPracticeRow])
def current_practices(department_id: int | None = None, user: User = Depends(require_viewer), db: Session = Depends(get_db)):
    scope = scope_department_id(user, department_id)
    return [
        CurrentPracticeRow(
            id=r.practice.id, study_group_id=r.group.id, group_code=r.group.code, course=r.group.course,
            department=r.group.department.name, kind_name=svc.KINDS.get(r.practice.kind, r.practice.kind),
            date_from=r.practice.date_from, date_to=r.practice.date_to, base=r.practice.base,
            college_supervisor=r.practice.college_supervisor, base_supervisor=r.practice.base_supervisor,
            phone=r.practice.phone, review_received=r.practice.review_received, state=r.state,
        )
        for r in svc.current(db, scope, today_local())
    ]


@router.get("/groups/{group_id}", response_model=GroupPracticesRead)
def group_practices(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    rows = db.execute(
        select(GroupPractice).where(GroupPractice.study_group_id == group.id).order_by(GroupPractice.date_from.desc())
    ).scalars().all()
    try:
        assert_can_access_group(db, user, group.id, today)
        can_edit = True
    except HTTPException:
        can_edit = False  # соц. педагог и психолог читают любую группу, а менять могут только свои
    return GroupPracticesRead(group_id=group.id, can_edit=can_edit, practices=[_read(p, today) for p in rows])


@router.post("/groups/{group_id}", response_model=PracticeRead, status_code=status.HTTP_201_CREATED)
def create_practice(group_id: int, payload: PracticeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    assert_can_access_group(db, user, group_id, today)
    group = _group(db, group_id)
    practice = GroupPractice(study_group_id=group.id, created_by_user_id=user.id)
    _apply(practice, payload, today)
    db.add(practice)
    db.flush()
    return _save(db, user, practice, "practice.create")


@router.put("/{practice_id}", response_model=PracticeRead)
def update_practice(practice_id: int, payload: PracticeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    practice = _practice(db, practice_id)
    assert_can_access_group(db, user, practice.study_group_id, today)
    _apply(practice, payload, today)
    db.flush()
    return _save(db, user, practice, "practice.update")


@router.delete("/{practice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_practice(practice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    practice = _practice(db, practice_id)
    assert_can_access_group(db, user, practice.study_group_id, today_local())
    svc.audit(db, user, "practice.delete", practice)
    svc.remove(db, practice, user)
    db.commit()
