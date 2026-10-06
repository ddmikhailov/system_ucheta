"""Отчёт куратора за семестр (этап 8): черновик из данных платформы, ручные показатели и выгрузка в Word.

Права — как у плана воспитательной работы: читать и выгружать — тем, кому открыт журнал группы; вносить цифры — тем, кто
работает с группой (куратор, заместитель, зав. отделением, тьютор, администрация). Особые данные досье в отчёт не входят."""
import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import StudyGroup, User
from app.services import curator_report_service as svc
from app.services import group_event_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/reports", tags=["reports"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FieldRead(BaseModel):
    key: str
    label: str
    hint: str | None
    long: bool
    auto: str | None  # что насчитала платформа
    value: str | None  # что внёс куратор


class SectionRead(BaseModel):
    key: str
    title: str
    fields: list[FieldRead]


class ReportRead(BaseModel):
    group_id: int
    group_code: str
    school_year: str
    semester: int
    period_from: datetime.date
    period_to: datetime.date
    years: list[str]
    sections: list[SectionRead]
    updated_at: datetime.datetime | None
    can_edit: bool


class ReportIn(BaseModel):
    values: dict[str, str | None] = Field(default_factory=dict)


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _period_params(year: str | None, semester: int | None, today: datetime.date) -> tuple[str, int]:
    year = year or group_event_service.school_year(today)
    if not group_event_service.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    return year, semester or svc.current_semester(today)


def _can_edit(db: Session, user: User, group_id: int, today: datetime.date) -> bool:
    try:
        assert_can_access_group(db, user, group_id, today)
    except HTTPException:
        return False
    return True


def _read(db: Session, group: StudyGroup, year: str, semester: int, user: User, today: datetime.date) -> ReportRead:
    stored, row = svc.stored_values(db, group.id, year, semester)
    auto = svc.auto_values(db, group, year, semester, today)
    start, end = svc.period(year, semester)
    years = {year, group_event_service.school_year(today)}
    return ReportRead(
        group_id=group.id, group_code=group.code, school_year=year, semester=semester, period_from=start, period_to=end,
        years=sorted(years, reverse=True),
        sections=[SectionRead(key=s.key, title=s.title, fields=[
            FieldRead(key=f.key, label=f.label, hint=f.hint, long=f.long, auto=auto.get(f.key), value=stored.get(f.key))
            for f in s.fields]) for s in svc.SECTIONS],
        updated_at=row.updated_at if row else None, can_edit=_can_edit(db, user, group.id, today),
    )


@router.get("/groups/{group_id}", response_model=ReportRead)
def group_report(
    group_id: int, year: str | None = Query(None, max_length=9), semester: int | None = Query(None, ge=1, le=2),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year, semester = _period_params(year, semester, today)
    return _read(db, group, year, semester, user, today)


@router.put("/groups/{group_id}", response_model=ReportRead)
def save_report(
    group_id: int, payload: ReportIn, year: str | None = Query(None, max_length=9), semester: int | None = Query(None, ge=1, le=2),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Ручные показатели семестра заменяются целиком (пустое значение — «взять посчитанное платформой»)."""
    today = today_local()
    assert_can_access_group(db, user, group_id, today)
    group = _group(db, group_id)
    year, semester = _period_params(year, semester, today)
    if any(v is not None and len(v) > svc.MAX_VALUE_LENGTH for v in payload.values.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Значение не длиннее {svc.MAX_VALUE_LENGTH} символов")
    try:
        saved = svc.save_values(db, group.id, year, semester, payload.values, user.id)
    except svc.UnknownField as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.flush()
    # Значения в журнал не пишем — только сколько показателей внесено.
    log_action(db, user, "report.save", "study_group", str(group.id), new_value=f"{year}/{semester}:{len(saved)}")
    result = _read(db, group, year, semester, user, today)
    db.commit()
    return result


@router.get("/groups/{group_id}/report.docx")
def report_docx(
    group_id: int, year: str | None = Query(None, max_length=9), semester: int | None = Query(None, ge=1, le=2),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Отчёт куратора в Word по образцу колледжа: внесённые значения, а где их нет — посчитанные платформой."""
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    group = _group(db, group_id)
    year, semester = _period_params(year, semester, today)
    stored, _ = svc.stored_values(db, group.id, year, semester)
    values = svc.effective_values(stored, svc.auto_values(db, group, year, semester, today))
    try:
        content = svc.build_docx(group_code=group.code, year=year, semester=semester, values=values)
    except svc.TemplateMismatch as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Образец отчёта повреждён: {exc}")
    log_action(db, user, "report.docx", "study_group", str(group.id), new_value=f"{year}/{semester}")
    db.commit()
    filename = quote(f"Отчёт_куратора_{group.code}_{semester}_семестр_{year}.docx")
    return Response(content=content, media_type=DOCX_MEDIA_TYPE,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})
