"""План воспитательной работы группы (этап 9): мероприятия группы, классные часы с присутствующими и выгрузка
в Word по образцам колледжа — план группы, план куратора, протокол классного часа.

Права: читать — тем, кому открыт журнал группы (куратор и заместитель своей группы, зав. отделением и тьютор — отделения,
администрация и воспитательный отдел — любой, соц. педагог и психолог — любой, только чтение); менять — тем, кто может
работать с группой (куратор, заместитель, зав. отделением, тьютор, администрация)."""
import datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import GroupEvent, GroupEventAttendee, StudyGroup, User
from app.services import group_event_service as svc
from app.services.audit_service import log_action

router = APIRouter(prefix="/events", tags=["events"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
Section = Literal["civic", "legal", "cultural", "spiritual", "sport", "professional", "psychology", "parents",
                  "group_org", "college", "career"]
Status = Literal["planned", "done", "cancelled"]


class EventIn(BaseModel):
    section: Section
    title: str = Field(min_length=1, max_length=500)
    event_date: datetime.date | None = None
    time_text: str | None = Field(default=None, max_length=32)
    responsible: str | None = Field(default=None, max_length=255)
    goal: str | None = Field(default=None, max_length=2000)
    status: Status = "planned"
    result: str | None = Field(default=None, max_length=2000)
    is_class_hour: bool = False
    description: str | None = Field(default=None, max_length=3000)
    school_year: str | None = Field(default=None, max_length=9)  # если даты нет — к какому учебному году относится


class EventRead(BaseModel):
    id: int
    study_group_id: int
    school_year: str
    section: str
    title: str
    event_date: datetime.date | None
    time_text: str | None
    responsible: str | None
    goal: str | None
    status: str
    result: str | None
    is_class_hour: bool
    description: str | None
    attendee_ids: list[int]


class StudentRef(BaseModel):
    id: int
    full_name: str


class PlanRead(BaseModel):
    group_id: int
    group_code: str
    school_year: str
    years: list[str]
    sections: list[dict[str, str]]
    events: list[EventRead]
    students: list[StudentRef]
    can_edit: bool


class AttendanceIn(BaseModel):
    student_ids: list[int]


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _event(db: Session, event_id: int) -> GroupEvent:
    event = db.get(GroupEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Мероприятие не найдено")
    return event


def _read(event: GroupEvent, attendees: dict[int, list[int]]) -> EventRead:
    return EventRead(
        id=event.id, study_group_id=event.study_group_id, school_year=event.school_year, section=event.section,
        title=event.title, event_date=event.event_date, time_text=event.time_text, responsible=event.responsible,
        goal=event.goal, status=event.status, result=event.result, is_class_hour=event.is_class_hour,
        description=event.description, attendee_ids=sorted(attendees.get(event.id, [])),
    )


def _can_edit(db: Session, user: User, group_id: int, today: datetime.date) -> bool:
    try:
        assert_can_access_group(db, user, group_id, today)
    except HTTPException:
        return False
    return True


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _apply(event: GroupEvent, payload: EventIn, today: datetime.date) -> None:
    year = svc.school_year(payload.event_date) if payload.event_date else (payload.school_year or event.school_year or svc.school_year(today))
    if not svc.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    event.school_year = year
    event.section = payload.section
    event.title = payload.title.strip()
    event.event_date = payload.event_date
    event.time_text = _clean(payload.time_text)
    event.responsible = _clean(payload.responsible)
    event.goal = _clean(payload.goal)
    event.status = payload.status
    event.result = _clean(payload.result)
    event.is_class_hour = payload.is_class_hour
    event.description = _clean(payload.description)


@router.get("/groups/{group_id}", response_model=PlanRead)
def group_plan(
    group_id: int, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = year or svc.school_year(today)
    if not svc.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    events = svc.events_of(db, group.id, year)
    attendees = svc.attendee_ids(db, [e.id for e in events])
    years = {y for (y,) in db.query(GroupEvent.school_year).filter(GroupEvent.study_group_id == group.id).distinct()}
    years |= {svc.school_year(today), year}
    return PlanRead(
        group_id=group.id, group_code=group.code, school_year=year, years=sorted(years, reverse=True),
        sections=[{"key": k, "title": t} for k, t in svc.SECTIONS], events=[_read(e, attendees) for e in events],
        students=[StudentRef(id=s.id, full_name=s.full_name) for s in svc.roster(db, group, today)],
        can_edit=_can_edit(db, user, group.id, today),
    )


@router.post("/groups/{group_id}", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(group_id: int, payload: EventIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    assert_can_access_group(db, user, group_id, today)
    group = _group(db, group_id)
    event = GroupEvent(study_group_id=group.id, created_by_user_id=user.id)
    _apply(event, payload, today)
    db.add(event)
    db.flush()
    log_action(db, user, "event.create", "study_group", str(group.id), new_value=str(event.id))
    result = _read(event, {})
    db.commit()
    return result


@router.put("/{event_id}", response_model=EventRead)
def update_event(event_id: int, payload: EventIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    event = _event(db, event_id)
    assert_can_access_group(db, user, event.study_group_id, today)
    _apply(event, payload, today)
    if not event.is_class_hour:
        db.query(GroupEventAttendee).filter(GroupEventAttendee.event_id == event.id).delete()
    db.flush()
    log_action(db, user, "event.update", "study_group", str(event.study_group_id), new_value=str(event.id))
    result = _read(event, svc.attendee_ids(db, [event.id]))
    db.commit()
    return result


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    event = _event(db, event_id)
    assert_can_access_group(db, user, event.study_group_id, today_local())
    db.query(GroupEventAttendee).filter(GroupEventAttendee.event_id == event.id).delete()
    db.delete(event)
    log_action(db, user, "event.delete", "study_group", str(event.study_group_id), old_value=str(event_id))
    db.commit()


@router.put("/{event_id}/attendance", response_model=EventRead)
def set_attendance(event_id: int, payload: AttendanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Кто присутствовал на классном часе: список заменяется целиком; только студенты группы."""
    today = today_local()
    event = _event(db, event_id)
    assert_can_access_group(db, user, event.study_group_id, today)
    if not event.is_class_hour:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Присутствующих отмечают только на классном часе")
    group = _group(db, event.study_group_id)
    allowed = {s.id for s in svc.roster(db, group, today)}
    chosen = list(dict.fromkeys(payload.student_ids))
    if not set(chosen) <= allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Среди присутствующих есть студент не из этой группы")
    db.query(GroupEventAttendee).filter(GroupEventAttendee.event_id == event.id).delete()
    db.add_all(GroupEventAttendee(event_id=event.id, student_id=sid) for sid in chosen)
    db.flush()
    log_action(db, user, "event.attendance", "study_group", str(event.study_group_id), new_value=f"{event.id}:{len(chosen)}")
    result = _read(event, {event.id: chosen})
    db.commit()
    return result


def _filename(prefix: str, code: str, today: datetime.date) -> str:
    return quote(f"{prefix}_{code}_{today.strftime('%d.%m.%Y')}.docx")


@router.get("/groups/{group_id}/plan.docx")
def plan_docx(
    group_id: int, kind: Literal["group", "curator"] = "group", year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """План воспитательной работы в Word по образцу колледжа: `kind=group` — план группы, `curator` — план куратора."""
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = year or svc.school_year(today)
    if not svc.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    try:
        content = svc.build_plan_docx(kind=kind, group_code=group.code, year=year, events=svc.events_of(db, group.id, year))
    except svc.TemplateMismatch as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Образец плана повреждён: {exc}")
    log_action(db, user, "event.plan_docx", "study_group", str(group.id), new_value=f"{kind}:{year}")
    db.commit()
    prefix = "План_группы" if kind == "group" else "План_куратора"
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_filename(prefix, group.code, today)}"})


@router.get("/{event_id}/protocol.docx")
def protocol_docx(event_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Протокол классного часа в Word по образцу колледжа (только для мероприятия с отметкой «классный час»)."""
    today = today_local()
    event = _event(db, event_id)
    assert_can_view_group(db, user, event.study_group_id, today)
    if not event.is_class_hour:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Протокол составляется для мероприятия с отметкой «классный час»")
    group = _group(db, event.study_group_id)
    students = svc.roster(db, group, today)
    chosen = set(svc.attendee_ids(db, [event.id])[event.id])
    present = [s.full_name for s in students if s.id in chosen]
    curator = next(
        (a.user.full_name for a in group.curator_assignments
         if a.role_type.value == "curator" and a.is_active_on(today) and a.user.is_active), None,
    )
    try:
        content = svc.build_protocol_docx(event=event, group_code=group.code, curator_name=curator,
                                          listed=len(students), present=present)
    except svc.TemplateMismatch as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Образец протокола повреждён: {exc}")
    log_action(db, user, "event.protocol_docx", "study_group", str(group.id), new_value=str(event.id))
    db.commit()
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_filename('Протокол_классного_часа', group.code, event.event_date or today)}"})
