import datetime
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AssignmentRole,
    CuratorAssignment,
    DaySubmission,
    Department,
    NotificationLog,
    StudyGroup,
    User,
)
from app.services import stats_service

settings = get_settings()


def get_responsible_user(db: Session, group: StudyGroup, date: datetime.date) -> User | None:
    """Кто отвечает за группу в этот день: активный заместитель важнее
    основного куратора (см. концепцию — на время замещения напоминания
    идут заместителю), иначе основной куратор, иначе никто (вакансия —
    эскалация на зав. отделением работает через другие витрины)."""
    assignments = (
        db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id == group.id).all()
    )
    deputy = next(
        (a for a in assignments if a.role_type == AssignmentRole.DEPUTY and a.is_active_on(date) and a.user.is_active),
        None,
    )
    if deputy is not None:
        return deputy.user

    curator = next(
        (a for a in assignments if a.role_type == AssignmentRole.CURATOR and a.is_active_on(date) and a.user.is_active),
        None,
    )
    return curator.user if curator else None


def groups_needing_reminder(db: Session, date: datetime.date) -> dict[User, list[StudyGroup]]:
    """Активные группы, которые ещё не сдали день, сгруппированные по
    тому, кому сейчас отвечать (куратор или его заместитель)."""
    groups = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).all()
    submitted_ids = {
        row.study_group_id
        for row in db.query(DaySubmission.study_group_id)
        .filter(DaySubmission.date == date, DaySubmission.study_group_id.in_([g.id for g in groups]))
        .all()
    }

    by_user: dict[User, list[StudyGroup]] = {}
    for group in groups:
        if group.id in submitted_ids:
            continue
        user = get_responsible_user(db, group, date)
        if user is None or user.telegram_chat_id is None:
            continue
        by_user.setdefault(user, []).append(group)
    return by_user


def was_notified(db: Session, user_id: int, kind: str, date: datetime.date) -> bool:
    return (
        db.query(NotificationLog)
        .filter(NotificationLog.user_id == user_id, NotificationLog.kind == kind, NotificationLog.date == date)
        .first()
        is not None
    )


def record_notification(db: Session, user_id: int, kind: str, date: datetime.date) -> None:
    db.add(NotificationLog(user_id=user_id, kind=kind, date=date))
    db.commit()


@dataclass
class DeptHeadDigestRow:
    group_code: str
    responsible_name: str | None


def dept_head_unsubmitted_groups(db: Session, department: Department, date: datetime.date) -> list[DeptHeadDigestRow]:
    groups = (
        db.query(StudyGroup)
        .filter(StudyGroup.department_id == department.id, StudyGroup.is_active.is_(True))
        .all()
    )
    submitted_ids = {
        row.study_group_id
        for row in db.query(DaySubmission.study_group_id)
        .filter(DaySubmission.date == date, DaySubmission.study_group_id.in_([g.id for g in groups]))
        .all()
    }
    rows = []
    for group in groups:
        if group.id in submitted_ids:
            continue
        responsible = get_responsible_user(db, group, date)
        rows.append(DeptHeadDigestRow(group_code=group.code, responsible_name=responsible.full_name if responsible else None))
    return rows


@dataclass
class CollegeSummary:
    total_groups: int
    submitted_groups: int
    percent: float
    problem_groups: list[str] = field(default_factory=list)


def college_day_summary(db: Session, date: datetime.date) -> CollegeSummary:
    rows = stats_service.day_overview(db, date)
    submitted = sum(1 for r in rows if r["is_submitted"])
    total_in_list = sum(r["in_list"] for r in rows)
    total_present = sum(r["present"] for r in rows)
    percent = round(total_present / total_in_list * 100, 1) if total_in_list else 0.0
    problem = [
        r["code"] for r in rows
        if r["in_list"] > 0 and r["percent"] < settings.problem_group_percent_threshold
    ]
    return CollegeSummary(
        total_groups=len(rows), submitted_groups=submitted, percent=percent, problem_groups=problem
    )


@dataclass
class LeadershipDigest:
    date_from: datetime.date
    date_to: datetime.date
    college_percent: float
    on_time_total: int
    late_total: int
    missed_total: int
    risk_students_count: int


def leadership_weekly_digest(db: Session, date_from: datetime.date, date_to: datetime.date) -> LeadershipDigest:
    stats = stats_service.compute_period_stats(db, date_from, date_to)
    discipline = stats_service.curator_discipline(db, date_from, date_to)
    risky = stats_service.risk_students(db, date_to, settings.risk_threshold_consecutive_unexcused)
    return LeadershipDigest(
        date_from=date_from,
        date_to=date_to,
        college_percent=stats.percent,
        on_time_total=sum(r["on_time"] for r in discipline),
        late_total=sum(r["late"] for r in discipline),
        missed_total=sum(r["missed"] for r in discipline),
        risk_students_count=len(risky),
    )


def leadership_recipients(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(
            User.receives_leadership_digest.is_(True),
            User.telegram_chat_id.isnot(None),
            User.is_active.is_(True),
        )
        .all()
    )


def edu_department_recipients(db: Session) -> list[User]:
    from app.models import Role, RoleCode

    role = db.query(Role).filter(Role.code == RoleCode.EDU_DEPARTMENT.value).one_or_none()
    if role is None:
        return []
    return db.query(User).filter(User.role_id == role.id, User.telegram_chat_id.isnot(None), User.is_active.is_(True)).all()


def dept_heads_with_telegram(db: Session) -> list[User]:
    from app.models import Role, RoleCode

    role = db.query(Role).filter(Role.code == RoleCode.DEPT_HEAD.value).one_or_none()
    if role is None:
        return []
    return db.query(User).filter(User.role_id == role.id, User.telegram_chat_id.isnot(None), User.is_active.is_(True)).all()
