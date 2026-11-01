"""Журнал преподавателя: загрузка выгрузки (оценки и «н»), успеваемость группы и сверка посещаемости.

Загрузка — как у контингента: «Предпросмотр» ничего не пишет, «Применить» записывает. Студенты из чужих групп
в файле пропускаются (запись — в зоне «edit» пользователя). Дневные отметки куратора не меняются."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import assert_can_view_group, require_roles
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, User
from app.services import journal_import_service as svc
from app.services import journal_view_service as view

router = APIRouter(prefix="/journal", tags=["journal"])

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_DAYS = 400
DEFAULT_DAYS = 30
journal_user = require_roles(*[r for r in RoleCode if r is not RoleCode.MEAL_MANAGER])


class ReportRead(BaseModel):
    subject_code: str
    subject_name: str
    period_from: datetime.date | None
    period_to: datetime.date | None
    counts: dict[str, int]
    warnings: list[str]
    not_found: list[str]
    ambiguous: list[str]
    out_of_scope: list[str]
    blocked: str | None
    applied: bool


class SubjectRead(BaseModel):
    code: str
    name: str


class SubjectStatRead(BaseModel):
    code: str
    count: int
    average: float | None
    twos: int
    low_average: bool
    absent_hours: int
    last_on: datetime.date | None


class StudentGradesRead(BaseModel):
    student_id: int
    full_name: str
    average: float | None
    subjects: list[SubjectStatRead]


class GradesRead(BaseModel):
    subjects: list[SubjectRead]
    students: list[StudentGradesRead]


class JournalSubjectRead(BaseModel):
    code: str
    name: str
    lessons: int
    first_on: datetime.date
    last_on: datetime.date


class LessonRead(BaseModel):
    key: str  # «2026-09-01#1»: ключ ячейки в cells
    date: datetime.date
    slot: int
    topic: str | None
    homework: str | None


class GridStudentRead(BaseModel):
    student_id: int
    full_name: str
    cells: dict[str, str]
    average: float | None
    absent_hours: int
    twos: int
    low_average: bool


class JournalGridRead(BaseModel):
    code: str
    name: str
    lessons: list[LessonRead]
    students: list[GridStudentRead]


class DiscrepancyRead(BaseModel):
    student_id: int
    full_name: str
    date: datetime.date
    hours: int
    subjects: list[str]
    curator_code: str | None
    kind: str


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise HTTPException(413, "Файл больше 5 МБ")
    content = await request.body()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл не передан")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Файл больше 5 МБ")
    return content


def _run(db: Session, user: User, content: bytes, apply: bool) -> ReportRead:
    today = today_local()
    try:
        parsed = svc.parse_workbook(content, today)
    except svc.ImportFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    report = svc.process(db, parsed, user, today)
    # Ответ собираем ДО commit(): после него объекты устаревают (см. CLAUDE.md).
    done = apply and report.blocked is None
    payload = ReportRead(
        subject_code=report.subject_code, subject_name=report.subject_name,
        period_from=report.period[0] if report.period else None, period_to=report.period[1] if report.period else None,
        counts=report.counts, warnings=report.warnings[: svc.MAX_LISTED],
        not_found=report.not_found[: svc.MAX_LISTED], ambiguous=report.ambiguous[: svc.MAX_LISTED],
        out_of_scope=report.out_of_scope[: svc.MAX_LISTED], blocked=report.blocked, applied=done,
    )
    if done:
        db.commit()
    else:
        db.rollback()
    return payload


@router.post("/preview", response_model=ReportRead)
async def preview(request: Request, user: User = Depends(journal_user), db: Session = Depends(get_db)):
    content = await _read_body(request)
    return await run_in_threadpool(_run, db, user, content, False)


@router.post("/apply", response_model=ReportRead)
async def apply(request: Request, user: User = Depends(journal_user), db: Session = Depends(get_db)):
    content = await _read_body(request)
    return await run_in_threadpool(_run, db, user, content, True)


def _period(date_from: datetime.date | None, date_to: datetime.date | None) -> tuple[datetime.date, datetime.date]:
    end = date_to or today_local()
    start = date_from or end - datetime.timedelta(days=DEFAULT_DAYS)
    if start > end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from не может быть позже date_to")
    if (end - start).days > MAX_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Период не может быть длиннее {MAX_DAYS} дней")
    return start, end


@router.get("/groups/{group_id}/grades", response_model=GradesRead)
def group_grades(
    group_id: int, date_from: datetime.date | None = None, date_to: datetime.date | None = None,
    user: User = Depends(journal_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    subjects, rows = view.group_grades(db, group_id, today, date_from, date_to)
    return GradesRead(
        subjects=[SubjectRead(code=c, name=n) for c, n in subjects],
        students=[
            StudentGradesRead(
                student_id=r.student_id, full_name=r.full_name, average=r.average,
                subjects=[
                    SubjectStatRead(code=s.code, count=s.count, average=s.average, twos=s.twos, low_average=view.is_low_average(s.average), absent_hours=s.absent_hours, last_on=s.last_on)
                    for s in r.subjects.values()
                ],
            ) for r in rows
        ],
    )


@router.get("/groups/{group_id}/discrepancies", response_model=list[DiscrepancyRead])
def group_discrepancies(
    group_id: int, date_from: datetime.date | None = None, date_to: datetime.date | None = None,
    user: User = Depends(journal_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    start, end = _period(date_from, date_to)
    return [DiscrepancyRead(**d.__dict__) for d in view.discrepancies(db, group_id, today, start, end)]


@router.get("/groups/{group_id}/subjects", response_model=list[JournalSubjectRead])
def group_subjects(group_id: int, user: User = Depends(journal_user), db: Session = Depends(get_db)):
    assert_can_view_group(db, user, group_id, today_local())
    return [JournalSubjectRead(**s.__dict__) for s in view.group_subjects(db, group_id)]


@router.get("/groups/{group_id}/subjects/{subject_code}", response_model=JournalGridRead)
def group_journal(
    group_id: int, subject_code: str, date_from: datetime.date | None = None, date_to: datetime.date | None = None,
    user: User = Depends(journal_user), db: Session = Depends(get_db),
):
    today = today_local()
    assert_can_view_group(db, user, group_id, today)
    lessons, students = view.journal_grid(db, group_id, subject_code, today, date_from, date_to)
    if not lessons:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Журнал этой дисциплины для группы не загружен")
    return JournalGridRead(
        code=subject_code, name=lessons[-1].subject_name,
        lessons=[LessonRead(key=f"{l.date.isoformat()}#{l.slot}", date=l.date, slot=l.slot, topic=l.topic, homework=l.homework) for l in lessons],
        students=[GridStudentRead(**s.__dict__) for s in students],
    )
