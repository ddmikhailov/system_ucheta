"""Вкладка «Мой ID» (раздел «Моя группа»): по каждому студенту — зарегистрирована ли биометрия «Мой.ID», есть ли он сам
и его родитель в чатах MAX и причины, если нет. Заполняется куратором вручную (как таблица в Excel, которую вели
раньше); данные из Excel в платформу пока не переносятся. Ответ «Да» / «Нет» ставится один раз и не исправляется.

Права: смотреть — тем, кому открыт журнал группы; заполнять — тем, кто работает с группой (куратор, заместитель,
зав. отделением, тьютор, администрация). Это обычные сведения студента, не особые категории; в журнал аудита пишется
только факт сохранения и число изменённых студентов."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, assert_can_view_group, get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import StudentMyId, StudyGroup, User
from app.services import group_event_service, passport_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/my-id", tags=["my-id"])

CHECKS = (("biometrics", "biometrics_reason"), ("max_student", "max_student_reason"), ("max_parent", "max_parent_reason"))


class MyIdRow(BaseModel):
    student_id: int
    full_name: str
    biometrics: bool | None = None
    biometrics_reason: str | None = None
    max_student: bool | None = None
    max_student_reason: str | None = None
    max_parent: bool | None = None
    max_parent_reason: str | None = None


class MyIdTotals(BaseModel):
    students: int
    biometrics_yes: int
    biometrics_no: int
    biometrics_unset: int
    max_student_yes: int
    max_student_no: int
    max_parent_yes: int
    max_parent_no: int


class MyIdRead(BaseModel):
    group_id: int
    group_code: str
    school_year: str
    can_edit: bool
    rows: list[MyIdRow]
    totals: MyIdTotals


class MyIdRowIn(BaseModel):
    student_id: int
    biometrics: bool | None = None
    biometrics_reason: str | None = Field(default=None, max_length=255)
    max_student: bool | None = None
    max_student_reason: str | None = Field(default=None, max_length=255)
    max_parent: bool | None = None
    max_parent_reason: str | None = Field(default=None, max_length=255)


class MyIdIn(BaseModel):
    rows: list[MyIdRowIn] = Field(max_length=200)


def _group(db: Session, group_id: int) -> StudyGroup:
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    return group


def _year(year: str | None, today: datetime.date) -> str:
    year = year or group_event_service.school_year(today)
    if not group_event_service.valid_school_year(year):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Учебный год в формате 2026-2027")
    return year


def _can_edit(db: Session, user: User, group_id: int, today: datetime.date) -> bool:
    try:
        assert_can_access_group(db, user, group_id, today)
    except HTTPException:
        return False
    return True


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _read(db: Session, group: StudyGroup, year: str, user: User, today: datetime.date) -> MyIdRead:
    students = passport_service.rosters(db, [group], today)[group.id]
    stored = {r.student_id: r for r in db.query(StudentMyId).filter(
        StudentMyId.school_year == year, StudentMyId.student_id.in_([s.id for s in students]))} if students else {}
    rows = []
    for s in students:
        r = stored.get(s.id)
        rows.append(MyIdRow(student_id=s.id, full_name=s.full_name, **({
            "biometrics": r.biometrics, "biometrics_reason": r.biometrics_reason, "max_student": r.max_student,
            "max_student_reason": r.max_student_reason, "max_parent": r.max_parent, "max_parent_reason": r.max_parent_reason,
        } if r else {})))
    count = lambda attr, value: sum(1 for row in rows if getattr(row, attr) is value)  # noqa: E731
    totals = MyIdTotals(
        students=len(rows), biometrics_yes=count("biometrics", True), biometrics_no=count("biometrics", False),
        biometrics_unset=count("biometrics", None), max_student_yes=count("max_student", True),
        max_student_no=count("max_student", False), max_parent_yes=count("max_parent", True), max_parent_no=count("max_parent", False),
    )
    return MyIdRead(group_id=group.id, group_code=group.code, school_year=year, can_edit=_can_edit(db, user, group.id, today),
                    rows=rows, totals=totals)


@router.get("/groups/{group_id}", response_model=MyIdRead)
def group_my_id(
    group_id: int, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    return _read(db, _group(db, group_id), _year(year, today), user, today)


@router.put("/groups/{group_id}", response_model=MyIdRead)
def save_my_id(
    group_id: int, payload: MyIdIn, year: str | None = Query(None, max_length=9),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Сохраняет отметки присланных студентов (остальные не трогает).

    Ответ «Да» / «Нет» ставится один раз и **исправить его нельзя**: если показатель уже отмечен, другое значение —
    409, а пустое (`null`) значит «не менять». Причина хранится только при «Нет» и дописывается при необходимости;
    при «Да» её нет."""
    today = today_local()
    assert_can_access_group(db, user, group_id, today)
    group = _group(db, group_id)
    year = _year(year, today)
    allowed = {s.id for s in passport_service.rosters(db, [group], today)[group.id]}
    sent = [r.student_id for r in payload.rows]
    if len(set(sent)) != len(sent):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Студент указан дважды")
    if not set(sent) <= allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Среди студентов есть не из этой группы")
    existing = {r.student_id: r for r in db.query(StudentMyId).filter(
        StudentMyId.school_year == year, StudentMyId.student_id.in_(sent))} if sent else {}

    # Сначала проверяем все строки, потом пишем: при конфликте не сохраняется ничего.
    for row in payload.rows:
        record = existing.get(row.student_id)
        for flag, _ in CHECKS:
            new, old = getattr(row, flag), getattr(record, flag) if record else None
            if old is not None and new is not None and new != old:
                raise HTTPException(status.HTTP_409_CONFLICT, "Ответ уже сохранён — исправить его нельзя")

    changed = 0
    for row in payload.rows:
        record = existing.get(row.student_id)
        if record is None:
            if all(getattr(row, flag) is None for flag, _ in CHECKS):
                continue  # пустую строку для студента, которого ещё не отмечали, не создаём
            record = StudentMyId(student_id=row.student_id, school_year=year)
            db.add(record)
        before = [getattr(record, a) for pair in CHECKS for a in pair]
        for flag, reason in CHECKS:
            value = getattr(row, flag)
            if value is None:
                value = getattr(record, flag)  # не прислано — оставляем как было
            setattr(record, flag, value)
            raw_reason = getattr(row, reason)
            if value is not False:
                setattr(record, reason, None)
            elif raw_reason is not None:  # прислано (в том числе пустое — стереть); не прислано — как было
                setattr(record, reason, _clean(raw_reason))
        if before != [getattr(record, a) for pair in CHECKS for a in pair]:
            record.updated_by_user_id = user.id
            changed += 1
    db.flush()
    log_action(db, user, "my_id.save", "study_group", str(group.id), new_value=f"{year}:{changed}")
    result = _read(db, group, year, user, today)
    db.commit()
    return result
