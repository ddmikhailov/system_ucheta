"""Успеваемость группы и сверка «н» из журнала преподавателя с дневными отметками куратора (данные — `lesson_marks`).

Дневные отметки посещаемости эти данные не меняют: расхождения только показываются, решает куратор."""
import datetime
from dataclasses import dataclass, field

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import AttendanceMark, JournalLesson, LessonMark, StudyGroup
from app.services import attendance_service
from app.services.journal_import_service import norm

LOW_GRADE = 2  # «двойка» = задолженность (решение Denis 29.10.2026)
LOW_AVERAGE = 4.0  # средняя оценка ниже этой подсвечивается куратору: помочь студенту исправить оценки


def is_low_average(average: float | None) -> bool:
    return average is not None and average < LOW_AVERAGE


@dataclass
class SubjectStat:
    code: str
    name: str
    count: int = 0
    total: int = 0
    twos: int = 0
    absent_hours: int = 0
    last_on: datetime.date | None = None

    @property
    def average(self) -> float | None:
        return round(self.total / self.count, 2) if self.count else None


@dataclass
class StudentGrades:
    student_id: int
    full_name: str
    subjects: dict[str, SubjectStat] = field(default_factory=dict)

    @property
    def average(self) -> float | None:
        count = sum(s.count for s in self.subjects.values())
        return round(sum(s.total for s in self.subjects.values()) / count, 2) if count else None


def _marks(db: Session, student_ids: list[int], date_from, date_to) -> list[LessonMark]:
    if not student_ids:
        return []
    query = db.query(LessonMark).filter(LessonMark.student_id.in_(student_ids))
    if date_from:
        query = query.filter(LessonMark.date >= date_from)
    if date_to:
        query = query.filter(LessonMark.date <= date_to)
    return query.all()


def group_grades(db: Session, group_id: int, today: datetime.date, date_from=None, date_to=None):
    """Средние баллы, двойки и часы «н» по студентам группы и дисциплинам."""
    students = attendance_service.get_active_students(db, group_id, today)
    rows = {s.id: StudentGrades(student_id=s.id, full_name=s.full_name) for s in students}
    subjects: dict[str, str] = {}
    for mark in _marks(db, list(rows), date_from, date_to):
        subjects[mark.subject_code] = mark.subject_name
        stat = rows[mark.student_id].subjects.setdefault(mark.subject_code, SubjectStat(mark.subject_code, mark.subject_name))
        if mark.absent:
            stat.absent_hours += 1
        if mark.grade is not None:
            stat.count += 1
            stat.total += mark.grade
            stat.twos += mark.grade <= LOW_GRADE
            stat.last_on = max(stat.last_on, mark.date) if stat.last_on else mark.date
    return sorted(subjects.items()), list(rows.values())


@dataclass
class Discrepancy:
    student_id: int
    full_name: str
    date: datetime.date
    hours: int
    subjects: list[str]
    curator_code: str | None  # None — отметки куратора за этот день нет
    kind: str  # "no_mark" — куратор день не отметил, "present" — куратор отметил присутствие


def discrepancies(db: Session, group_id: int, today: datetime.date, date_from: datetime.date, date_to: datetime.date) -> list[Discrepancy]:
    """Дни, когда преподаватель поставил «н», а куратор отметил присутствие или не отметил день вовсе."""
    students = attendance_service.get_active_students(db, group_id, today)
    names = {s.id: s.full_name for s in students}
    if not names:
        return []
    absent: dict[tuple[int, datetime.date], list[LessonMark]] = {}
    for mark in _marks(db, list(names), date_from, date_to):
        if mark.absent:
            absent.setdefault((mark.student_id, mark.date), []).append(mark)
    if not absent:
        return []
    day_marks = {
        (m.student_id, m.date): m
        for m in db.query(AttendanceMark).options(joinedload(AttendanceMark.mark_code))
        .filter(AttendanceMark.student_id.in_(list(names)), AttendanceMark.date >= date_from, AttendanceMark.date <= date_to)
    }
    result: list[Discrepancy] = []
    for (student_id, day), marks in sorted(absent.items(), key=lambda kv: (kv[0][1], names[kv[0][0]])):
        mark = day_marks.get((student_id, day))
        if mark is not None and not mark.mark_code.counts_as_present:
            continue  # куратор тоже отметил отсутствие (с причиной или без): расхождения нет
        result.append(Discrepancy(
            student_id=student_id, full_name=names[student_id], date=day, hours=len(marks),
            subjects=sorted({m.subject_name for m in marks}),
            curator_code=mark.mark_code.code if mark is not None else None,
            kind="present" if mark is not None else "no_mark",
        ))
    return result


def _group_lessons_query(db: Session, group_id: int):
    group = db.get(StudyGroup, group_id)
    code = norm(group.code) if group else ""
    base = code.split(".")[0]
    patterns = {f"%,{code},%", f"%,{base},%", f"%,{base}.%"}  # код группы как в подписи, без «.9» или с подгруппой
    return db.query(JournalLesson).filter(or_(*[JournalLesson.group_key.like(p) for p in patterns]))


@dataclass
class SubjectRow:
    code: str
    name: str
    lessons: int
    first_on: datetime.date
    last_on: datetime.date


def group_subjects(db: Session, group_id: int) -> list[SubjectRow]:
    """Дисциплины, журналы которых загружены для группы (группа названа в подписи выгрузки)."""
    rows = (
        _group_lessons_query(db, group_id)
        .with_entities(JournalLesson.subject_code, func.max(JournalLesson.subject_name), func.count(JournalLesson.id),
                       func.min(JournalLesson.date), func.max(JournalLesson.date))
        .group_by(JournalLesson.subject_code).order_by(JournalLesson.subject_code).all()
    )
    return [SubjectRow(code, name, count, first, last) for code, name, count, first, last in rows]


@dataclass
class GridStudent:
    student_id: int
    full_name: str
    cells: dict[str, str]  # «2026-09-01#1» → «5» или «н»
    average: float | None
    absent_hours: int
    twos: int
    low_average: bool


def journal_grid(db: Session, group_id: int, subject_code: str, today: datetime.date, date_from=None, date_to=None):
    """Журнал дисциплины как у преподавателя: часы по столбцам, студенты группы по строкам.
    Пустая ячейка — присутствовал, оценки нет (так в самой выгрузке)."""
    lessons = _group_lessons_query(db, group_id).filter(JournalLesson.subject_code == subject_code)
    if date_from:
        lessons = lessons.filter(JournalLesson.date >= date_from)
    if date_to:
        lessons = lessons.filter(JournalLesson.date <= date_to)
    lessons = lessons.order_by(JournalLesson.date, JournalLesson.slot).all()
    students = attendance_service.get_active_students(db, group_id, today)
    ids = [s.id for s in students]
    cells: dict[int, dict[str, str]] = {sid: {} for sid in ids}
    stats = {sid: [0, 0, 0, 0] for sid in ids}  # число оценок, сумма, часы «н», двойки
    if ids and lessons:
        marks = db.query(LessonMark).filter(
            LessonMark.student_id.in_(ids), LessonMark.subject_code == subject_code,
            LessonMark.date >= lessons[0].date, LessonMark.date <= lessons[-1].date,
        )
        for m in marks:
            cells[m.student_id][f"{m.date.isoformat()}#{m.slot}"] = "н" if m.absent else str(m.grade)
            st = stats[m.student_id]
            if m.absent:
                st[2] += 1
            elif m.grade is not None:
                st[0] += 1
                st[1] += m.grade
                st[3] += m.grade <= LOW_GRADE
    rows = [
        GridStudent(
            student_id=s.id, full_name=s.full_name, cells=cells[s.id],
            average=round(stats[s.id][1] / stats[s.id][0], 2) if stats[s.id][0] else None,
            absent_hours=stats[s.id][2], twos=stats[s.id][3],
            low_average=is_low_average(round(stats[s.id][1] / stats[s.id][0], 2) if stats[s.id][0] else None),
        ) for s in students
    ]
    return lessons, rows
