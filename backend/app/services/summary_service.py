"""Свод посещаемости для выгрузки: по дням, по группам, по отделениям и по
всему колледжу — «всего» и отдельно «к 1 паре» (группы, которые в этот день
пришли к первой паре; пару выставляет куратор при сдаче дня).

Считается пачкой запросов на весь период, а не по запросу на каждую пару
«группа — день»: в колледже ~45 групп × ~22 учебных дня в месяце."""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceMark,
    DaySubmission,
    Department,
    MarkCode,
    Student,
    StudentGroupMembership,
    StudyGroup,
)
from app.services import calendar_service, group_scope

FIRST_PERIOD = 1


@dataclass
class GroupDayRow:
    date: datetime.date
    group_id: int
    group_code: str
    course: int
    department_id: int
    department_name: str
    headcount: int
    is_submitted: bool
    first_period: int | None
    # Заполняется только у сданных дней: у несданного отметок нет, и «все
    # пришли» там означало бы «мы ничего не знаем» (см. stats_service).
    absent: int = 0
    by_code: dict[str, int] = field(default_factory=dict)

    @property
    def present(self) -> int:
        return self.headcount - self.absent if self.is_submitted else 0


@dataclass
class SummaryTotals:
    groups: int = 0
    groups_submitted: int = 0
    headcount: int = 0
    counted: int = 0
    present: int = 0
    absent: int = 0
    by_code: dict[str, int] = field(default_factory=dict)

    @property
    def percent(self) -> float | None:
        if self.counted == 0:
            return None
        return round(self.present / self.counted * 100, 2)

    def add(self, row: GroupDayRow) -> None:
        self.groups += 1
        self.headcount += row.headcount
        if not row.is_submitted:
            return
        self.groups_submitted += 1
        self.counted += row.headcount
        self.present += row.present
        self.absent += row.absent
        for code, n in row.by_code.items():
            self.by_code[code] = self.by_code.get(code, 0) + n


def totals_for(rows: list[GroupDayRow]) -> SummaryTotals:
    totals = SummaryTotals()
    for row in rows:
        totals.add(row)
    return totals


def is_pair(row: GroupDayRow, pair: int) -> bool:
    return row.is_submitted and row.first_period == pair


def is_first_period(row: GroupDayRow) -> bool:
    return is_pair(row, FIRST_PERIOD)


def collect_group_day_rows(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
) -> list[GroupDayRow]:
    stmt = (
        select(StudyGroup, Department.name)
        .join(Department, Department.id == StudyGroup.department_id)
        .where(StudyGroup.is_active.is_(True), group_scope.has_curator())
    )
    if department_id is not None:
        stmt = stmt.where(StudyGroup.department_id == department_id)
    if course is not None:
        stmt = stmt.where(StudyGroup.course == course)
    if study_group_id is not None:
        stmt = stmt.where(StudyGroup.id == study_group_id)
    group_rows = db.execute(stmt.order_by(StudyGroup.course, StudyGroup.code)).all()
    if not group_rows:
        return []
    group_ids = [g.id for g, _ in group_rows]

    memberships = db.execute(
        select(StudentGroupMembership).where(
            StudentGroupMembership.study_group_id.in_(group_ids),
            StudentGroupMembership.start_date <= date_to,
            (StudentGroupMembership.end_date.is_(None)) | (StudentGroupMembership.end_date >= date_from),
        )
    ).scalars().all()
    student_ids = {m.student_id for m in memberships}
    students = (
        {s.id: s for s in db.execute(select(Student).where(Student.id.in_(student_ids))).scalars().all()}
        if student_ids
        else {}
    )
    memberships_by_group: dict[int, list[StudentGroupMembership]] = defaultdict(list)
    for m in memberships:
        memberships_by_group[m.study_group_id].append(m)

    marks_by_student_date: dict[tuple[int, datetime.date], tuple[str, bool]] = {}
    if student_ids:
        for row in db.execute(
            select(AttendanceMark.student_id, AttendanceMark.date, MarkCode.code, MarkCode.counts_as_present)
            .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
            .where(
                AttendanceMark.student_id.in_(student_ids),
                AttendanceMark.date >= date_from,
                AttendanceMark.date <= date_to,
            )
        ).all():
            marks_by_student_date[(row.student_id, row.date)] = (row.code, row.counts_as_present)

    submissions = {
        (s.study_group_id, s.date): s
        for s in db.execute(
            select(DaySubmission).where(
                DaySubmission.study_group_id.in_(group_ids),
                DaySubmission.date >= date_from,
                DaySubmission.date <= date_to,
            )
        ).scalars().all()
    }

    result: list[GroupDayRow] = []
    for group, department_name in group_rows:
        study_days = calendar_service.study_days_between(
            db, date_from, date_to, study_group_id=group.id, course=group.course
        )
        for day in study_days:
            roster = [
                students[m.student_id]
                for m in memberships_by_group.get(group.id, [])
                if m.is_active_on(day)
                and students[m.student_id].enrolled_at <= day
                and (students[m.student_id].left_at is None or students[m.student_id].left_at >= day)
            ]
            submission = submissions.get((group.id, day))
            row = GroupDayRow(
                date=day,
                group_id=group.id,
                group_code=group.code,
                course=group.course,
                department_id=group.department_id,
                department_name=department_name,
                headcount=len(roster),
                is_submitted=submission is not None,
                first_period=submission.first_period if submission else None,
            )
            if submission is not None:
                for student in roster:
                    mark = marks_by_student_date.get((student.id, day))
                    if mark is None:
                        continue
                    code, counts_as_present = mark
                    row.by_code[code] = row.by_code.get(code, 0) + 1
                    if not counts_as_present:
                        row.absent += 1
            result.append(row)
    return result


ALL_DEPARTMENTS_LABEL = "Все отделения"
SLICE_ALL = "Всего"
SLICE_FIRST_PERIOD = "К 1 паре"


def pair_slice_label(pair: int) -> str:
    return f"К {pair} паре"


@dataclass
class SummaryLine:
    """Одна строка свода: отделение (или «Все отделения») × срез («Всего» /
    «К 1 паре»), за один день (`date`) или за весь период (`date is None`)."""

    date: datetime.date | None
    department: str
    slice_name: str
    groups: int
    totals: SummaryTotals


@dataclass
class Summary:
    codes: list["CodeColumn"]  # столбцы по кодам отметок
    daily: list[SummaryLine]
    period: list[SummaryLine]
    group_days: list[GroupDayRow]


@dataclass
class CodeColumn:
    code: str
    name: str
    counts_as_present: bool


def code_columns(db: Session, rows: list[GroupDayRow]) -> list[CodeColumn]:
    """Сначала активные коды по sort_order, затем встретившиеся в данных, но
    уже отключённые — иначе отметки по отключённому коду молча пропали бы."""
    all_codes = db.execute(select(MarkCode).order_by(MarkCode.sort_order, MarkCode.id)).scalars().all()
    used = {code for row in rows for code in row.by_code}
    return [CodeColumn(c.code, c.name, c.counts_as_present) for c in all_codes if c.is_active or c.code in used]


def _slices(rows: list[GroupDayRow], pair: int):
    yield SLICE_ALL, rows
    yield pair_slice_label(pair), [r for r in rows if is_pair(r, pair)]


def _scopes(rows: list[GroupDayRow], departments: list[str]):
    scopes = [(name, [r for r in rows if r.department_name == name]) for name in departments]
    if len(departments) > 1:
        scopes.append((ALL_DEPARTMENTS_LABEL, rows))
    return scopes


def build_summary(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    pair: int = FIRST_PERIOD,
) -> Summary:
    rows = collect_group_day_rows(db, date_from, date_to, department_id, course, study_group_id)
    departments = sorted({r.department_name for r in rows})

    daily: list[SummaryLine] = []
    for day in sorted({r.date for r in rows}):
        day_rows = [r for r in rows if r.date == day]
        for scope_name, scope_rows in _scopes(day_rows, departments):
            if not scope_rows:
                continue
            for slice_name, slice_rows in _slices(scope_rows, pair):
                daily.append(
                    SummaryLine(day, scope_name, slice_name, len({r.group_id for r in slice_rows}), totals_for(slice_rows))
                )

    period: list[SummaryLine] = []
    for scope_name, scope_rows in _scopes(rows, departments):
        if not scope_rows:
            continue
        for slice_name, slice_rows in _slices(scope_rows, pair):
            period.append(
                SummaryLine(None, scope_name, slice_name, len({r.group_id for r in slice_rows}), totals_for(slice_rows))
            )

    group_days = sorted(rows, key=lambda x: (x.date, x.department_name, x.group_code))
    return Summary(codes=code_columns(db, rows), daily=daily, period=period, group_days=group_days)
