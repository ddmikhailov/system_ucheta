"""Родительские собрания группы (этап 10): учёт собраний, явка родителей и протокол в Word по образцу колледжа.

Права — как у плана воспитательной работы (`events.py`): читать — тем, кому открыт журнал группы; менять — тем, кто
работает с группой. Список представителей для отметки явки — обычные контакты досье (ФИО, кем приходится, студент);
телефоны и особые данные в ответ и в протокол не попадают."""
import datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import ParentMeeting, ParentMeetingAttendee, StudyGroup, User
from app.services import parent_meeting_service as svc
from app.services.audit_service import log_action

router = APIRouter(prefix="/meetings", tags=["meetings"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class MeetingIn(BaseModel):
    number: int | None = Field(default=None, ge=1, le=99)  # по умолчанию — следующий в учебном году
    meeting_date: datetime.date | None = None
    agenda: str | None = Field(default=None, max_length=3000)
    staff: str | None = Field(default=None, max_length=2000)
    speakers: str | None = Field(default=None, max_length=2000)
    meeting_format: Literal["in_person", "remote"] = "in_person"
    parents_count: int | None = Field(default=None, ge=0, le=500)
    listened: str | None = Field(default=None, max_length=5000)
    resolved: str | None = Field(default=None, max_length=5000)
    school_year: str | None = Field(default=None, max_length=9)  # если даты нет


class MeetingRead(BaseModel):
    id: int
    study_group_id: int
    school_year: str
    number: int
    meeting_date: datetime.date | None
    agenda: str | None
    staff: str | None
    speakers: str | None
    meeting_format: str
    parents_count: int | None
    listened: str | None
    resolved: str | None
    attendee_ids: list[int]


class GuardianRef(BaseModel):
    id: int
    full_name: str
    relation: str
    student_name: str


class MeetingsRead(BaseModel):
    group_id: int
    school_year: str
    meetings: list[MeetingRead]
    guardians: list[GuardianRef]


class AttendanceIn(BaseModel):
    guardian_ids: list[int]


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _meeting(db: Session, meeting_id: int) -> ParentMeeting:
    meeting = db.get(ParentMeeting, meeting_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Собрание не найдено")
    return meeting


def _read(m: ParentMeeting, attendees: dict[int, list[int]]) -> MeetingRead:
    return MeetingRead(
        id=m.id, study_group_id=m.study_group_id, school_year=m.school_year, number=m.number, meeting_date=m.meeting_date,
        agenda=m.agenda, staff=m.staff, speakers=m.speakers, meeting_format=m.meeting_format, parents_count=m.parents_count,
        listened=m.listened, resolved=m.resolved, attendee_ids=sorted(attendees.get(m.id, [])),
    )


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _apply(db: Session, meeting: ParentMeeting, payload: MeetingIn, today: datetime.date) -> None:
    year = svc.school_year(payload.meeting_date) if payload.meeting_date else (payload.school_year or meeting.school_year or svc.school_year(today))
    if not svc.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    meeting.school_year = year
    meeting.number = payload.number or meeting.number or svc.next_number(db, meeting.study_group_id, year)
    meeting.meeting_date = payload.meeting_date
    meeting.agenda = _clean(payload.agenda)
    meeting.staff = _clean(payload.staff)
    meeting.speakers = _clean(payload.speakers)
    meeting.meeting_format = payload.meeting_format
    meeting.parents_count = payload.parents_count
    meeting.listened = _clean(payload.listened)
    meeting.resolved = _clean(payload.resolved)


@router.get("/groups/{group_id}", response_model=MeetingsRead)
def group_meetings(
    group_id: int, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = year or svc.school_year(today)
    if not svc.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    meetings = svc.meetings_of(db, group.id, year)
    attendees = svc.attendee_ids(db, [m.id for m in meetings])
    return MeetingsRead(
        group_id=group.id, school_year=year, meetings=[_read(m, attendees) for m in meetings],
        guardians=[GuardianRef(id=g.id, full_name=g.full_name, relation=g.relation, student_name=s.full_name)
                   for g, s in svc.group_guardians(db, group, today)],
    )


@router.post("/groups/{group_id}", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
def create_meeting(group_id: int, payload: MeetingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    assert_can_access_group(db, user, group_id, today)
    group = _group(db, group_id)
    meeting = ParentMeeting(study_group_id=group.id, created_by_user_id=user.id, number=0)  # 0 — номер ещё не выбран
    _apply(db, meeting, payload, today)
    db.add(meeting)
    db.flush()
    log_action(db, user, "meeting.create", "study_group", str(group.id), new_value=str(meeting.id))
    result = _read(meeting, {})
    db.commit()
    return result


@router.put("/{meeting_id}", response_model=MeetingRead)
def update_meeting(meeting_id: int, payload: MeetingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    meeting = _meeting(db, meeting_id)
    assert_can_access_group(db, user, meeting.study_group_id, today)
    _apply(db, meeting, payload, today)
    db.flush()
    log_action(db, user, "meeting.update", "study_group", str(meeting.study_group_id), new_value=str(meeting.id))
    result = _read(meeting, svc.attendee_ids(db, [meeting.id]))
    db.commit()
    return result


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    meeting = _meeting(db, meeting_id)
    assert_can_access_group(db, user, meeting.study_group_id, today_local())
    db.query(ParentMeetingAttendee).filter(ParentMeetingAttendee.meeting_id == meeting.id).delete()
    db.delete(meeting)
    log_action(db, user, "meeting.delete", "study_group", str(meeting.study_group_id), old_value=str(meeting_id))
    db.commit()


@router.put("/{meeting_id}/attendance", response_model=MeetingRead)
def set_attendance(meeting_id: int, payload: AttendanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Кто из родителей присутствовал: список заменяется целиком; только представители студентов группы."""
    today = today_local()
    meeting = _meeting(db, meeting_id)
    assert_can_access_group(db, user, meeting.study_group_id, today)
    group = _group(db, meeting.study_group_id)
    allowed = {g.id for g, _ in svc.group_guardians(db, group, today)}
    chosen = list(dict.fromkeys(payload.guardian_ids))
    if not set(chosen) <= allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Среди присутствующих есть человек не из представителей этой группы")
    db.query(ParentMeetingAttendee).filter(ParentMeetingAttendee.meeting_id == meeting.id).delete()
    db.add_all(ParentMeetingAttendee(meeting_id=meeting.id, guardian_id=gid) for gid in chosen)
    db.flush()
    log_action(db, user, "meeting.attendance", "study_group", str(meeting.study_group_id), new_value=f"{meeting.id}:{len(chosen)}")
    result = _read(meeting, {meeting.id: chosen})
    db.commit()
    return result


@router.get("/{meeting_id}/protocol.docx")
def protocol_docx(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Протокол родительского собрания в Word по образцу колледжа."""
    today = today_local()
    meeting = _meeting(db, meeting_id)
    assert_can_view_group(db, user, meeting.study_group_id, today)
    group = _group(db, meeting.study_group_id)
    chosen = set(svc.attendee_ids(db, [meeting.id])[meeting.id])
    parents = [g.full_name for g, _ in svc.group_guardians(db, group, today) if g.id in chosen]
    curator = next(
        (a.user.full_name for a in group.curator_assignments
         if a.role_type.value == "curator" and a.is_active_on(today) and a.user.is_active), None,
    )
    try:
        content = svc.build_protocol_docx(meeting=meeting, group_code=group.code, curator_name=curator, parents=parents)
    except svc.TemplateMismatch as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Образец протокола повреждён: {exc}")
    log_action(db, user, "meeting.protocol_docx", "study_group", str(group.id), new_value=str(meeting.id))
    db.commit()
    when = (meeting.meeting_date or today).strftime("%d.%m.%Y")
    filename = quote(f"Протокол_родительского_собрания_{group.code}_{when}.docx")
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})
