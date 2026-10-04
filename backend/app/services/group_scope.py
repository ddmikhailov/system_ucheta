"""Какие группы попадают в общие перечни.

Правило: в общем перечне (день, дисциплина кураторов, «Свод», выгрузки) —
только группы, на которых сейчас назначен действующий куратор. Группы без
куратора в нём не учитываются и показываются отдельно — на вкладке
«Вакантные группы» (там же зав. отделением назначает куратора).
"""
import datetime

from sqlalchemy import or_, select

from app.core.time import today_local
from app.models import AssignmentRole, CuratorAssignment, StudyGroup, User


def has_curator(on_date: datetime.date | None = None):
    """Условие SQLAlchemy: у группы на дату (по умолчанию сегодня) есть куратор —
    не заместитель, и сам пользователь не отключён."""
    day = on_date or today_local()
    with_curator_ids = (
        select(CuratorAssignment.study_group_id)
        .join(User, User.id == CuratorAssignment.user_id)
        .where(
            CuratorAssignment.role_type == AssignmentRole.CURATOR,
            User.is_active.is_(True),
            CuratorAssignment.start_date <= day,
            or_(CuratorAssignment.end_date.is_(None), CuratorAssignment.end_date >= day),
        )
    )
    return StudyGroup.id.in_(with_curator_ids)
