import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.config import get_settings
from app.core.time import today_local
from app.db.session import get_db
from app.models import DaySubmission, DayType, MarkCode, Student, StudyGroup, User
from app.schemas.curator import (
    AbsencePeriodCreate,
    GroupSummary,
    MonthDayStatus,
    RosterResponse,
    SubmitDayRequest,
)
from app.services import attendance_service, calendar_service, group_list_service, my_day_service, student_card_service
from app.services.audit_service import log_action
from app.schemas.my_day import RhythmDay
from app.services.access_service import get_curator_group_ids

router = APIRouter(prefix="/curator", tags=["curator"])
settings = get_settings()


@router.get("/settings")
def curator_settings(user: User = Depends(get_current_user)):
    # Порог «группы риска» берётся из того же значения, что реально использует бэкенд.
    return {"risk_attendance_percent": settings.risk_attendance_percent, "risk_min_days": settings.risk_min_days}


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
    today = today_local()
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
    assert_can_view_group(db, user, study_group_id, date)
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
            db, study_group_id, date, [e.model_dump() for e in payload.exceptions], user,
            first_period=payload.first_period,
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
    first_period: int | None = Query(default=None, ge=1, le=10),
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
        attendance_service.submit_day(db, study_group_id, date, [], user, first_period=first_period)
    except attendance_service.BackdateNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return attendance_service.get_roster(db, study_group_id, date)


@router.get("/groups/{study_group_id}/rhythm", response_model=list[RhythmDay])
def group_rhythm(study_group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """«Ритм группы» за три недели: тем же, кому открыт журнал группы (куратор, зав. отделением, администрация)."""
    today = today_local()
    assert_can_view_group(db, user, study_group_id, today)
    group = db.get(StudyGroup, study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return my_day_service.rhythm_for_group(db, group, today)


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/groups/{study_group_id}/roster-sheet")
def roster_sheet(
    study_group_id: int,
    fields: str = Query(..., description="Столбцы через запятую, например full_name,phone,email"),
    numbering: bool = True,
    title: str | None = Query(None, max_length=group_list_service.MAX_TITLE_LENGTH),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """«Список группы» для печати (.docx) — таблица с выбранными столбцами (ФИО, телефон, e-mail, адреса,
    представители, пустые столбцы для подписи…). Особые категории досье в список не попадают. Тем же, кому
    открыт журнал группы: куратор — своей, зав. отделением и тьютор — отделения, администрация — любой."""
    today = today_local()
    assert_can_view_group(db, user, study_group_id, today)
    group = db.get(StudyGroup, study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    try:
        chosen = group_list_service.parse_fields(fields)
    except group_list_service.UnknownField as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    rows = group_list_service.collect_rows(db, group, today, chosen)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В группе нет студентов")
    curator = next(
        (a.user.full_name for a in group.curator_assignments
         if a.role_type.value == "curator" and a.is_active_on(today) and a.user.is_active),
        None,
    )
    content = group_list_service.build_docx(
        group_code=group.code, department_name=group.department.name, curator_name=curator, on_date=today,
        fields=chosen, rows=rows, numbering=numbering, title=title,
    )
    log_action(db, user, "group.roster_sheet", "study_group", str(group.id), new_value=",".join(f.key for f in chosen))
    db.commit()
    filename = f"Список_{group.code}_{today:%d.%m.%Y}.docx"
    return Response(
        content=content, media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=\"roster_sheet.docx\"; filename*=UTF-8''{quote(filename)}"},
    )


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
    assert_can_view_group(db, user, study_group_id, datetime.date(year, month, 1))
    group = db.get(StudyGroup, study_group_id)

    date_from = datetime.date(year, month, 1)
    if month == 12:
        date_to = datetime.date(year, 12, 31)
    else:
        date_to = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    today = today_local()
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
    today = today_local()
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


@router.get("/groups/{study_group_id}/cards")
def group_cards(
    study_group_id: int,
    fields: str = Query(..., description="Поля карточки через запятую, например full_name,group,birth_date"),
    blank_sections: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Личные карточки всех студентов группы в одном Word-файле (каждая с новой страницы) по образцу колледжа.
    Куратор выбирает поля, остальные остаются пустыми строками бланка. Доступ — как у журнала группы."""
    today = today_local()
    assert_can_view_group(db, user, study_group_id, today)
    group = db.get(StudyGroup, study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    try:
        chosen = student_card_service.parse_fields(fields)
    except student_card_service.UnknownField as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    cards = student_card_service.collect(db, group, today)
    if not cards:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В группе нет студентов")
    try:
        content = student_card_service.build_docx(cards, chosen, blank_sections=blank_sections)
    except student_card_service.TemplateMismatch as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Образец карточки повреждён: {exc}")
    log_action(db, user, "group.student_cards", "study_group", str(group.id), new_value=",".join(chosen))
    db.commit()
    filename = f"Личные_карточки_{group.code}_{today.strftime('%d.%m.%Y')}.docx"
    return Response(
        content=content, media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
