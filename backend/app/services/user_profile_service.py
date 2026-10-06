"""Профиль пользователя для администрации: за какими группами закреплён, как сдаёт дни,
что с задачами и индивидуальной работой, и журнал его действий.

Всё считается из уже хранящихся данных (закрепления, сдачи дней, отметки, задачи, записи
досье, журнал аудита) — отдельного учёта «активности» нет. Запросов — фиксированное число,
не зависящее от числа групп и дней."""

import datetime
from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.time import today_local, utc_to_local, utcnow
from app.models import (
    AttendanceMark,
    AuditLog,
    CuratorAssignment,
    DaySubmission,
    DossierAccessLog,
    Student,
    StudentNote,
    StudyGroup,
    Task,
    TaskAssignment,
    User,
)
from app.models.enums import StudentStatus
from app.schemas.admin import (
    UserActivityDay,
    UserActivityEntry,
    UserActivityPage,
    UserDiscipline,
    UserGroupLink,
    UserTaskStats,
)
from app.services import calendar_service

PERIOD_DAYS = 30
TASK_WINDOW_DAYS = 90
ACTIVITY_PAGE_MAX = 100


def _groups(db: Session, user: User, today: datetime.date) -> tuple[list[UserGroupLink], list[CuratorAssignment]]:
    assignments = (
        db.query(CuratorAssignment)
        .options(joinedload(CuratorAssignment.study_group).joinedload(StudyGroup.department))
        .filter(CuratorAssignment.user_id == user.id)
        .order_by(CuratorAssignment.start_date.desc(), CuratorAssignment.id.desc())
        .all()
    )
    group_ids = {a.study_group_id for a in assignments}
    counts = dict(
        db.query(Student.study_group_id, func.count(Student.id))
        .filter(Student.study_group_id.in_(group_ids), Student.status == StudentStatus.STUDYING)
        .group_by(Student.study_group_id)
        .all()
    ) if group_ids else {}
    links = [
        UserGroupLink(
            group_id=a.study_group_id,
            group_code=a.study_group.code,
            course=a.study_group.course,
            department_name=a.study_group.department.name if a.study_group.department else None,
            role_type=a.role_type.value,
            start_date=a.start_date,
            end_date=a.end_date,
            is_current=a.is_active_on(today) and a.study_group.is_active,
            students_count=counts.get(a.study_group_id, 0),
        )
        for a in assignments
    ]
    # Текущие закрепления идут первыми, внутри — как были (свежие сверху).
    links.sort(key=lambda link: not link.is_current)
    current = [a for a in assignments if a.is_active_on(today) and a.study_group.is_active]
    return links, current


def _discipline(db: Session, current: list[CuratorAssignment], today: datetime.date) -> UserDiscipline:
    date_to = today - datetime.timedelta(days=1)
    date_from = today - datetime.timedelta(days=PERIOD_DAYS)
    # Одна группа может быть у человека и куратором, и заместителем — считаем её один раз,
    # с самой ранней даты начала.
    starts: dict[int, datetime.date] = {}
    groups: dict[int, StudyGroup] = {}
    for a in current:
        groups[a.study_group_id] = a.study_group
        starts[a.study_group_id] = min(a.start_date, starts.get(a.study_group_id, a.start_date))
    days = calendar_service.study_days_by_group(db, date_from, date_to, list(groups.values()))
    expected = {(gid, d) for gid, ds in days.items() for d in ds if d >= starts[gid]}

    submissions = (
        db.query(DaySubmission.study_group_id, DaySubmission.date, DaySubmission.is_on_time)
        .filter(
            DaySubmission.study_group_id.in_(groups.keys()),
            DaySubmission.date >= date_from,
            DaySubmission.date <= date_to,
        )
        .all()
    ) if groups else []
    on_time = late = 0
    for gid, day, is_on_time in submissions:
        if (gid, day) not in expected:
            continue
        if is_on_time:
            on_time += 1
        else:
            late += 1
    submitted = on_time + late
    return UserDiscipline(
        date_from=date_from,
        date_to=date_to,
        study_days=len(expected),
        submitted=submitted,
        on_time=on_time,
        late=late,
        missed=len(expected) - submitted,
        percent_on_time=round(on_time * 100 / len(expected)) if expected else None,
    )


def _tasks(db: Session, current: list[CuratorAssignment], today: datetime.date) -> UserTaskStats:
    group_ids = {a.study_group_id for a in current}
    if not group_ids:
        return UserTaskStats(total=0, accepted=0, submitted=0, in_work=0, returned=0, overdue=0)
    rows = (
        db.query(TaskAssignment.status, TaskAssignment.locked, Task.due_date)
        .join(Task, Task.id == TaskAssignment.task_id)
        .filter(
            TaskAssignment.study_group_id.in_(group_ids),
            Task.due_date >= today - datetime.timedelta(days=TASK_WINDOW_DAYS),
        )
        .all()
    )
    statuses = Counter(status for status, _, _ in rows)
    overdue = sum(
        1 for status, locked, due in rows if status not in ("accepted", "submitted") and not locked and due < today
    )
    return UserTaskStats(
        total=len(rows),
        accepted=statuses["accepted"],
        submitted=statuses["submitted"],
        in_work=statuses["new"] + statuses["in_progress"],
        returned=statuses["returned"],
        overdue=overdue,
    )


def build_profile(db: Session, user: User) -> dict:
    """Всё, кроме карточки самого пользователя (её собирает роутер, как в списке)."""
    today = today_local()
    since = utcnow() - datetime.timedelta(days=PERIOD_DAYS)
    links, current = _groups(db, user, today)

    marks_created = (
        db.query(func.count(AttendanceMark.id))
        .filter(AttendanceMark.created_by_user_id == user.id, AttendanceMark.created_at >= since)
        .scalar()
    )
    days_submitted = (
        db.query(func.count(DaySubmission.id))
        .filter(DaySubmission.submitted_by_user_id == user.id, DaySubmission.submitted_at >= since)
        .scalar()
    )
    notes_written = (
        db.query(func.count(StudentNote.id))
        .filter(StudentNote.author_id == user.id, StudentNote.created_at >= since)
        .scalar()
    )
    follow_ups_open = (
        db.query(func.count(StudentNote.id))
        .filter(
            StudentNote.author_id == user.id,
            StudentNote.follow_up_on.is_not(None),
            StudentNote.follow_up_done.is_(False),
        )
        .scalar()
    )
    dossier_views = (
        db.query(func.count(DossierAccessLog.id))
        .filter(DossierAccessLog.user_id == user.id, DossierAccessLog.created_at >= since)
        .scalar()
    )
    last_activity_at = db.query(func.max(AuditLog.created_at)).filter(AuditLog.user_id == user.id).scalar()

    # Ритм активности: сколько действий в журнале за каждый из 30 дней (по местному времени).
    per_day = Counter(
        utc_to_local(created_at).date()
        for (created_at,) in db.query(AuditLog.created_at)
        .filter(AuditLog.user_id == user.id, AuditLog.created_at >= since - datetime.timedelta(days=1))
        .all()
    )
    activity = [
        UserActivityDay(date=day, count=per_day.get(day, 0))
        for day in (today - datetime.timedelta(days=offset) for offset in range(PERIOD_DAYS - 1, -1, -1))
    ]

    return {
        "department_name": user.department.name if user.department else None,
        "created_at": user.created_at,
        "last_activity_at": last_activity_at,
        "groups": links,
        "discipline": _discipline(db, current, today),
        "tasks": _tasks(db, current, today),
        "marks_created_30d": marks_created or 0,
        "days_submitted_30d": days_submitted or 0,
        "notes_written_30d": notes_written or 0,
        "follow_ups_open": follow_ups_open or 0,
        "dossier_views_30d": dossier_views or 0,
        "activity_30d": activity,
    }


def activity_page(
    db: Session, user: User, before_id: int | None = None, limit: int = 50, prefix: str | None = None
) -> UserActivityPage:
    """Журнал действий человека, новые сверху. Листается «ещё» по id (стабильно, пока
    добавляются новые записи). `prefix` — область: «mark», «day», «task», «dossier»…"""
    limit = min(max(limit, 1), ACTIVITY_PAGE_MAX)
    query = db.query(AuditLog).filter(AuditLog.user_id == user.id)
    if before_id is not None:
        query = query.filter(AuditLog.id < before_id)
    if prefix:
        query = query.filter(AuditLog.action.like(f"{prefix}.%"))
    rows = query.order_by(AuditLog.id.desc()).limit(limit + 1).all()
    items = [
        UserActivityEntry(
            id=r.id, action=r.action, entity_type=r.entity_type, entity_id=r.entity_id, created_at=r.created_at
        )
        for r in rows[:limit]
    ]
    return UserActivityPage(items=items, next_before_id=items[-1].id if len(rows) > limit else None)
