"""Журнал инструктажа по охране труда группы (п. 5.1.15 положения): записи и печатный бланк для подписей студентов.

Права — как у родительских собраний (`meetings.py`): читать и печатать — тем, кому открыт журнал группы; менять — тем,
кто работает с группой. В бланк попадают только ФИО студентов; подписи ставятся на бумаге."""
import datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import SafetyInstruction, StudyGroup, User
from app.services import attendance_service
from app.services import safety_instruction_service as svc
from app.services.audit_service import log_action

router = APIRouter(prefix="/instructions", tags=["instructions"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
Kind = Literal["introductory", "primary", "repeated", "targeted", "unplanned"]


class InstructionIn(BaseModel):
    instruction_date: datetime.date
    kind: Kind
    topic: str = Field(min_length=1, max_length=500)
    conducted_by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class InstructionRead(BaseModel):
    id: int
    study_group_id: int
    school_year: str
    instruction_date: datetime.date
    kind: str
    kind_label: str
    topic: str
    conducted_by: str | None
    note: str | None


class InstructionsRead(BaseModel):
    group_id: int
    school_year: str
    instructions: list[InstructionRead]
    kinds: dict[str, str]
    can_edit: bool


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _record(db: Session, record_id: int) -> SafetyInstruction:
    record = db.get(SafetyInstruction, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись инструктажа не найдена")
    return record


def _read(r: SafetyInstruction) -> InstructionRead:
    return InstructionRead(
        id=r.id, study_group_id=r.study_group_id, school_year=r.school_year, instruction_date=r.instruction_date,
        kind=r.kind, kind_label=svc.KINDS.get(r.kind, r.kind), topic=r.topic, conducted_by=r.conducted_by, note=r.note,
    )


def _apply(record: SafetyInstruction, payload: InstructionIn) -> None:
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите тему инструктажа")
    record.instruction_date = payload.instruction_date
    record.school_year = svc.school_year(payload.instruction_date)
    record.kind = payload.kind
    record.topic = topic
    record.conducted_by = (payload.conducted_by or "").strip() or None
    record.note = (payload.note or "").strip() or None


@router.get("/groups/{group_id}", response_model=InstructionsRead)
def group_instructions(
    group_id: int, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = year or svc.school_year(today)
    if not svc.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    try:
        assert_can_access_group(db, user, group_id, today)
        can_edit = True
    except HTTPException:
        can_edit = False
    return InstructionsRead(
        group_id=group.id, school_year=year, instructions=[_read(r) for r in svc.records_of(db, group.id, year)],
        kinds=svc.KINDS, can_edit=can_edit,
    )


@router.post("/groups/{group_id}", response_model=InstructionRead, status_code=status.HTTP_201_CREATED)
def create_instruction(group_id: int, payload: InstructionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_can_access_group(db, user, group_id, today_local())
    group = _group(db, group_id)
    record = SafetyInstruction(study_group_id=group.id, created_by_user_id=user.id)
    _apply(record, payload)
    db.add(record)
    db.flush()
    log_action(db, user, "instruction.create", "study_group", str(group.id), new_value=str(record.id))
    result = _read(record)
    db.commit()
    return result


@router.put("/{record_id}", response_model=InstructionRead)
def update_instruction(record_id: int, payload: InstructionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = _record(db, record_id)
    assert_can_access_group(db, user, record.study_group_id, today_local())
    _apply(record, payload)
    db.flush()
    log_action(db, user, "instruction.update", "study_group", str(record.study_group_id), new_value=str(record.id))
    result = _read(record)
    db.commit()
    return result


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instruction(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = _record(db, record_id)
    assert_can_access_group(db, user, record.study_group_id, today_local())
    db.delete(record)
    log_action(db, user, "instruction.delete", "study_group", str(record.study_group_id), old_value=str(record_id))
    db.commit()


@router.get("/{record_id}/blank.docx")
def blank_docx(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Бланк для подписей: шапка записи и весь список группы на сегодня."""
    today = today_local()
    record = _record(db, record_id)
    assert_can_view_group(db, user, record.study_group_id, today)
    group = _group(db, record.study_group_id)
    students = [s.full_name for s in attendance_service.get_active_students(db, group.id, today)]
    if not students:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В группе нет студентов")
    curator = next(
        (a.user.full_name for a in group.curator_assignments
         if a.role_type.value == "curator" and a.is_active_on(today) and a.user.is_active), None,
    )
    content = svc.build_blank_docx(
        record=record, group_code=group.code, department_name=group.department.name, curator_name=curator, students=students,
    )
    log_action(db, user, "instruction.blank_docx", "study_group", str(group.id), new_value=str(record.id))
    db.commit()
    filename = quote(f"Инструктаж_{group.code}_{record.instruction_date:%d.%m.%Y}.docx")
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})
