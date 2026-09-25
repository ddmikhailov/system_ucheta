import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, get_current_user, get_curator_group_ids
from app.core.config import get_settings
from app.db.session import get_db
from app.models import DaySubmission, DayType, MarkCode, Student, StudyGroup, User
from app.schemas.curator import (
    AbsencePeriodCreate,
    GroupSummary,
    MonthDayStatus,
    RosterResponse,
    SubmitDayRequest,
)
from app.services import attendance_service, calendar_service

router = APIRouter(prefix="/curator", tags=["curator"])
settings = get_settings()


@router.get("/settings")
def curator_settings(user: User = Depends(get_current_user)):
    # Порог "риска" был захардкожен во фронте (см. TODO.md 4) — теперь
    # берётся из того же значения, что реально использует бэкенд при
    # расчёте risk_students.
    return {"risk_threshold_consecutive_unexcused": settings.risk_threshold_consecutive_unexcused}


@router.get("/mark-codes")
def mark_codes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(MarkCode).filter(MarkCode.is_active.is_(True)).order_by(MarkCode.sort_order).all()
    # is_excused нужен фронту, чтобы не предлагать неуважительные коды в
    # форме "Длительное отсутствие" (см. TODO.md 3) — раньше поле не
    # отдавалось вовсе, хотя фронтовый тип уже давно его ожидал.
    return [
        {
            "id": r.id, "code": r.code, "name": r.name, "counts_as_present": r.counts_as_present,
            "is_excused": r.is_excused, "requires_document": r.requires_document, "is_active": r.is_active,
        }
        for r in rows
    ]


@router.get("/groups", response_model=list[GroupSummary])
def my_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.date.today()
    group_ids = get_curator_group_ids(db, user, today)
    result = []
    for group_id in group_ids:
        roster = attendance_service.get_roster(db, group_id, today)
        group = next(a.study_group for a in user.curator_assignments if a.study_group_id == group_id)
        result.append(
            GroupSummary(id=group_id, code=group.code, course=group.course, is_submitted_today=roster["is_submitted"])
        )
    return result


@router.get("/groups/{study_group_id}/day", response_model=RosterResponse)
def get_day(
    study_group_id: int,
    date: datetime.date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_can_access_group(db, user, study_group_id, date)
    return attendance_service.get_roster(db, study_group_id, date)


@router.post("/groups/{study_group_id}/day/submit", response_model=RosterResponse)
def submit_day(
    study_group_id: int,
    date: datetime.date,
    payload: SubmitDayRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_can_access_group(db, user, study_group_id, date)
    try:
        attendance_service.submit_day(
            db, study_group_id, date, [e.model_dump() for e in payload.exceptions], user
        )
    except attendance_service.BackdateNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except attendance_service.InvalidSubmission as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return attendance_service.get_roster(db, study_group_id, date)


@router.post("/groups/{study_group_id}/day/mark-all-present", response_model=RosterResponse)
def mark_all_present(
    study_group_id: int,
    date: datetime.date,
    confirm: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_can_access_group(db, user, study_group_id, date)
    # "Все присутствуют" отправляет пустой список исключений — submit_day
    # молча удаляет все уже стоящие ручные отметки за этот день. Если день
    # уже сдан не пустым (в нём есть реальные отметки), требуем явного
    # подтверждения, а не стираем их без предупреждения (см. TODO.md 1.8).
    if not confirm:
        at_risk = attendance_service.count_manual_exceptions(db, study_group_id, date)
        if at_risk > 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"На этот день уже внесено отметок: {at_risk}. Они будут стёрты — "
                "повторите запрос с confirm=true, если это действительно нужно.",
            )
    try:
        attendance_service.submit_day(db, study_group_id, date, [], user)
    except attendance_service.BackdateNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return attendance_service.get_roster(db, study_group_id, date)


@router.get("/groups/{study_group_id}/month-status", response_model=list[MonthDayStatus])
def month_status(
    study_group_id: int,
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        # datetime.date(year, 13, 1) роняет ValueError -> необработанный 500
        # (см. TODO.md 3).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректные год/месяц")
    assert_can_access_group(db, user, study_group_id, datetime.date(year, month, 1))
    group = db.get(StudyGroup, study_group_id)

    date_from = datetime.date(year, month, 1)
    if month == 12:
        date_to = datetime.date(year, 12, 31)
    else:
        date_to = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    today = datetime.date.today()
    if date_to > today:
        date_to = today

    submissions = {
        s.date: s
        for s in db.query(DaySubmission)
        .filter(DaySubmission.study_group_id == study_group_id)
        .filter(DaySubmission.date >= date_from, DaySubmission.date <= date_to)
        .all()
    }

    result = []
    current = date_from
    while current <= date_to:
        resolved_type = calendar_service.resolve_day_type(
            db, current, study_group_id=study_group_id, course=group.course if group else None
        )
        is_study = resolved_type in (DayType.STUDY_DAY, DayType.REMOTE)
        submission = submissions.get(current)
        result.append(
            MonthDayStatus(
                date=current,
                day_type=resolved_type.value,
                is_submitted=(submission is not None) if is_study else None,
                is_on_time=submission.is_on_time if submission else None,
            )
        )
        current += datetime.timedelta(days=1)
    return result


@router.post("/absence-periods", status_code=status.HTTP_201_CREATED)
def create_absence_period(
    payload: AbsencePeriodCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")

    # Раньше не проверялось совсем (см. TODO.md 3): период мог кончаться
    # раньше, чем начинался (даты просто менялись местами при расчёте, и
    # период создавался пустым — 201 без единой отметки), тянуться на годы
    # вперёд (первый же такой period клал бы сервер расчётом study_days на
    # тысячи дат) или уходить в будущее.
    if payload.date_to < payload.date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Дата окончания раньше даты начала")
    if (payload.date_to - payload.date_from).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Период не может быть длиннее года")
    today = datetime.date.today()
    if payload.date_to > today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Период не может уходить в будущее")

    assert_can_access_group(db, user, student.study_group_id, payload.date_from)
    assert_can_access_group(db, user, student.study_group_id, payload.date_to)

    mark_code = db.query(MarkCode).filter(MarkCode.code == payload.mark_code).one_or_none()
    if mark_code is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестный код отметки")
    if not mark_code.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Этот код отметки отключён")
    if not mark_code.is_excused:
        # Длительный период — это "уважительная причина на много дней"
        # (больничный, приказ и т.п.). "Опоздание"/"ушёл с занятий"/
        # "неуважительная причина" тут не имеют смысла — они про конкретный
        # день, а не про отсутствие подряд (см. TODO.md 3).
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Для длительного периода нужен код с уважительной причиной"
        )

    period = attendance_service.create_absence_period(
        db, student.id, mark_code.id, payload.date_from, payload.date_to, payload.basis_reference, user
    )
    return {"id": period.id}
