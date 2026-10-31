"""Общие собрания студентов группы (п. 5.1.10 положения о кураторе): учёт и протокол в Word.

Права — как у родительских собраний (`meetings.py`): читать — тем, кому открыт журнал группы; менять — тем, кто
работает с группой. В протокол попадают только введённые данные и число студентов группы, без поимённых списков."""
import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import GroupAssembly, StudyGroup, User
from app.services import attendance_service, group_assembly_service as svc, group_event_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/assemblies", tags=["assemblies"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class AssemblyIn(BaseModel):
    number: int | None = Field(default=None, ge=1, le=99)  # по умолчанию — следующий в учебном году
    assembly_date: datetime.date | None = None
    chair: str | None = Field(default=None, max_length=255)
    secretary: str | None = Field(default=None, max_length=255)
    present_count: int | None = Field(default=None, ge=0, le=500)
    agenda: str | None = Field(default=None, max_length=3000)
    listened: str | None = Field(default=None, max_length=5000)
    resolved: str | None = Field(default=None, max_length=5000)
    school_year: str | None = Field(default=None, max_length=9)  # если даты нет


class AssemblyRead(BaseModel):
    id: int
    study_group_id: int
    school_year: str
    number: int
    assembly_date: datetime.date | None
    chair: str | None
    secretary: str | None
    present_count: int | None
    agenda: str | None
    listened: str | None
    resolved: str | None


class AssembliesRead(BaseModel):
    group_id: int
    school_year: str
    students_count: int
    assemblies: list[AssemblyRead]


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _assembly(db: Session, assembly_id: int) -> GroupAssembly:
    assembly = db.get(GroupAssembly, assembly_id)
    if assembly is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Собрание не найдено")
    return assembly


def _read(a: GroupAssembly) -> AssemblyRead:
    return AssemblyRead(
        id=a.id, study_group_id=a.study_group_id, school_year=a.school_year, number=a.number, assembly_date=a.assembly_date,
        chair=a.chair, secretary=a.secretary, present_count=a.present_count, agenda=a.agenda, listened=a.listened, resolved=a.resolved,
    )


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _apply(db: Session, assembly: GroupAssembly, payload: AssemblyIn, today: datetime.date) -> None:
    year = (group_event_service.school_year(payload.assembly_date) if payload.assembly_date
            else (payload.school_year or assembly.school_year or group_event_service.school_year(today)))
    if not group_event_service.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    assembly.school_year = year
    assembly.number = payload.number or assembly.number or svc.next_number(db, assembly.study_group_id, year)
    assembly.assembly_date = payload.assembly_date
    assembly.chair = _clean(payload.chair)
    assembly.secretary = _clean(payload.secretary)
    assembly.present_count = payload.present_count
    assembly.agenda = _clean(payload.agenda)
    assembly.listened = _clean(payload.listened)
    assembly.resolved = _clean(payload.resolved)


@router.get("/groups/{group_id}", response_model=AssembliesRead)
def group_assemblies(
    group_id: int, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = year or group_event_service.school_year(today)
    if not group_event_service.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    return AssembliesRead(
        group_id=group.id, school_year=year, students_count=len(attendance_service.get_active_students(db, group.id, today)),
        assemblies=[_read(a) for a in svc.assemblies_of(db, group.id, year)],
    )


@router.post("/groups/{group_id}", response_model=AssemblyRead, status_code=status.HTTP_201_CREATED)
def create_assembly(group_id: int, payload: AssemblyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    assert_can_access_group(db, user, group_id, today)
    group = _group(db, group_id)
    assembly = GroupAssembly(study_group_id=group.id, created_by_user_id=user.id, number=0)  # 0 — номер ещё не выбран
    _apply(db, assembly, payload, today)
    db.add(assembly)
    db.flush()
    log_action(db, user, "assembly.create", "study_group", str(group.id), new_value=str(assembly.id))
    result = _read(assembly)
    db.commit()
    return result


@router.put("/{assembly_id}", response_model=AssemblyRead)
def update_assembly(assembly_id: int, payload: AssemblyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    assembly = _assembly(db, assembly_id)
    assert_can_access_group(db, user, assembly.study_group_id, today)
    _apply(db, assembly, payload, today)
    db.flush()
    log_action(db, user, "assembly.update", "study_group", str(assembly.study_group_id), new_value=str(assembly.id))
    result = _read(assembly)
    db.commit()
    return result


@router.delete("/{assembly_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assembly(assembly_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assembly = _assembly(db, assembly_id)
    assert_can_access_group(db, user, assembly.study_group_id, today_local())
    db.delete(assembly)
    log_action(db, user, "assembly.delete", "study_group", str(assembly.study_group_id), old_value=str(assembly_id))
    db.commit()


@router.get("/{assembly_id}/protocol.docx")
def protocol_docx(assembly_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Протокол общего собрания группы в Word."""
    today = today_local()
    assembly = _assembly(db, assembly_id)
    assert_can_view_group(db, user, assembly.study_group_id, today)
    group = _group(db, assembly.study_group_id)
    curator = next(
        (a.user.full_name for a in group.curator_assignments
         if a.role_type.value == "curator" and a.is_active_on(today) and a.user.is_active), None,
    )
    content = svc.build_protocol_docx(
        assembly=assembly, group_code=group.code, curator_name=curator,
        listed=len(attendance_service.get_active_students(db, group.id, today)),
    )
    log_action(db, user, "assembly.protocol_docx", "study_group", str(group.id), new_value=str(assembly.id))
    db.commit()
    when = (assembly.assembly_date or today).strftime("%d.%m.%Y")
    filename = quote(f"Протокол_общего_собрания_{group.code}_{when}.docx")
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})
