"""В общих перечнях — только группы с действующим куратором."""
import datetime

from app.models import AssignmentRole, CuratorAssignment, StudyGroup, User
from app.services import group_scope, stats_service

VACANT = "ИИ132"  # в тестовой выгрузке — вакансия


def codes(rows):
    return {r["group_code"] if "group_code" in r else r["code"] for r in rows}


def group(db, code):
    return db.query(StudyGroup).filter_by(code=code).one()


def first_curator(db):
    return db.query(User).filter(User.password_hash.is_(None)).first()


def test_vacant_group_is_not_in_the_general_overview(imported, db, today):
    rows = stats_service.day_overview(db, today)

    assert VACANT not in codes(rows)
    assert len(rows) == 41  # 44 группы минус 3 вакантные
    assert VACANT not in codes(stats_service.curator_discipline(db, today, today))


def test_group_joins_the_overview_once_a_curator_is_assigned(imported, db, today):
    g = group(db, VACANT)
    db.add(CuratorAssignment(study_group_id=g.id, user_id=first_curator(db).id,
                             role_type=AssignmentRole.CURATOR, start_date=datetime.date(2026, 9, 1)))
    db.commit()

    assert VACANT in codes(stats_service.day_overview(db, today))


def test_deputy_or_ended_assignment_or_disabled_user_does_not_count(imported, db, today):
    g = group(db, VACANT)
    curator = first_curator(db)
    db.add(CuratorAssignment(study_group_id=g.id, user_id=curator.id,
                             role_type=AssignmentRole.DEPUTY, start_date=datetime.date(2026, 9, 1)))
    db.add(CuratorAssignment(study_group_id=g.id, user_id=curator.id, role_type=AssignmentRole.CURATOR,
                             start_date=datetime.date(2026, 9, 1), end_date=today - datetime.timedelta(days=1)))
    db.commit()
    assert VACANT not in codes(stats_service.day_overview(db, today))

    # у обычной группы отключённый куратор — группа тоже вакантна
    other = db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id != g.id).first()
    other_group = db.get(StudyGroup, other.study_group_id)
    db.get(User, other.user_id).is_active = False
    db.commit()
    assert other_group.code not in codes(stats_service.day_overview(db, today))


def test_condition_can_be_checked_for_a_past_date(imported, db):
    g = group(db, VACANT)
    db.add(CuratorAssignment(study_group_id=g.id, user_id=first_curator(db).id, role_type=AssignmentRole.CURATOR,
                             start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2026, 9, 10)))
    db.commit()

    in_september = db.query(StudyGroup.code).filter(group_scope.has_curator(datetime.date(2026, 9, 5))).all()
    in_october = db.query(StudyGroup.code).filter(group_scope.has_curator(datetime.date(2026, 10, 1))).all()

    assert (VACANT,) in in_september and (VACANT,) not in in_october
