"""Доступ к группам: какие группы ведёт пользователь."""
import datetime

from sqlalchemy.orm import Session

from app.models import CuratorAssignment, StudyGroup, User


def get_curator_group_ids(db: Session, user: User, on_date: datetime.date) -> list[int]:
    """Группы, которые ведёт пользователь (сам или как заместитель) на указанную дату."""
    assignments = (
        db.query(CuratorAssignment)
        .join(StudyGroup, StudyGroup.id == CuratorAssignment.study_group_id)
        # Архивная группа не должна оставаться в "Моих группах" куратора —
        # она снята с работы, отмечать в ней посещаемость больше не нужно
        # (см. TODO.md 3).
        .filter(CuratorAssignment.user_id == user.id, StudyGroup.is_active.is_(True))
        .all()
    )
    return [a.study_group_id for a in assignments if a.is_active_on(on_date)]
