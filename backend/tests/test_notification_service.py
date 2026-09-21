import datetime

from app.models import AssignmentRole, CuratorAssignment
from app.services import attendance_service, notification_service

DAY1 = datetime.date(2026, 9, 21)  # понедельник


def test_get_responsible_user_returns_curator_by_default(imported, db, curator_group, curator_user):
    responsible = notification_service.get_responsible_user(db, curator_group, DAY1)
    assert responsible.id == curator_user.id


def test_deputy_overrides_curator_during_active_window(imported, db, curator_group, curator_user):
    from app.models import Role, RoleCode, User
    from app.core.security import hash_password

    deputy_role = db.query(Role).filter(Role.code == RoleCode.DEPUTY_CURATOR.value).one()
    deputy = User(username="deputy1", full_name="Заместитель Тестов", role_id=deputy_role.id, password_hash=hash_password("x"))
    db.add(deputy)
    db.commit()

    db.add(
        CuratorAssignment(
            study_group_id=curator_group.id, user_id=deputy.id, role_type=AssignmentRole.DEPUTY,
            start_date=DAY1, end_date=DAY1 + datetime.timedelta(days=3),
        )
    )
    db.commit()

    responsible_during = notification_service.get_responsible_user(db, curator_group, DAY1 + datetime.timedelta(days=1))
    assert responsible_during.id == deputy.id

    responsible_after = notification_service.get_responsible_user(db, curator_group, DAY1 + datetime.timedelta(days=10))
    assert responsible_after.id == curator_user.id


def test_groups_needing_reminder_excludes_submitted_and_unlinked(imported, db, curator_group, curator_user):
    curator_user.telegram_chat_id = "12345"
    db.commit()

    by_user = notification_service.groups_needing_reminder(db, DAY1)
    assert any(u.id == curator_user.id for u in by_user)
    assert curator_group.id in [g.id for g in by_user[curator_user]]

    attendance_service.submit_day(db, curator_group.id, DAY1, [], curator_user, today=DAY1)

    by_user_after = notification_service.groups_needing_reminder(db, DAY1)
    remaining = by_user_after.get(curator_user, [])
    assert curator_group.id not in [g.id for g in remaining]


def test_groups_needing_reminder_skips_users_without_telegram(imported, db, curator_group, curator_user):
    assert curator_user.telegram_chat_id is None
    by_user = notification_service.groups_needing_reminder(db, DAY1)
    assert curator_user not in by_user


def test_notification_log_idempotency(imported, db, curator_user):
    assert notification_service.was_notified(db, curator_user.id, "reminder_1", DAY1) is False
    notification_service.record_notification(db, curator_user.id, "reminder_1", DAY1)
    assert notification_service.was_notified(db, curator_user.id, "reminder_1", DAY1) is True
    # другой день или другой вид напоминания — независимая запись
    assert notification_service.was_notified(db, curator_user.id, "reminder_2", DAY1) is False
    assert notification_service.was_notified(db, curator_user.id, "reminder_1", DAY1 + datetime.timedelta(days=1)) is False


def test_dept_head_unsubmitted_groups(imported, db, dept_head_user, curator_group, curator_user):
    rows = notification_service.dept_head_unsubmitted_groups(db, dept_head_user.department, DAY1)
    assert any(r.group_code == curator_group.code for r in rows)

    attendance_service.submit_day(db, curator_group.id, DAY1, [], curator_user, today=DAY1)

    rows_after = notification_service.dept_head_unsubmitted_groups(db, dept_head_user.department, DAY1)
    assert not any(r.group_code == curator_group.code for r in rows_after)


def test_college_day_summary(imported, db, curator_group, curator_user):
    summary = notification_service.college_day_summary(db, DAY1)
    assert summary.total_groups == 44
    assert summary.submitted_groups == 0

    attendance_service.submit_day(db, curator_group.id, DAY1, [], curator_user, today=DAY1)

    summary_after = notification_service.college_day_summary(db, DAY1)
    assert summary_after.submitted_groups == 1


def test_leadership_recipients_filters_by_flag_and_telegram(imported, db, admin_headers, curator_user):
    from app.models import User

    admin = db.query(User).filter(User.username == "admin").one()
    assert notification_service.leadership_recipients(db) == []

    admin.receives_leadership_digest = True
    db.commit()
    assert notification_service.leadership_recipients(db) == []  # ещё нет telegram

    admin.telegram_chat_id = "999"
    db.commit()
    recipients = notification_service.leadership_recipients(db)
    assert len(recipients) == 1
    assert recipients[0].id == admin.id


def test_edu_department_and_dept_head_recipients(imported, db, edu_department_user, dept_head_user):
    assert notification_service.edu_department_recipients(db) == []
    assert notification_service.dept_heads_with_telegram(db) == []

    edu_department_user.telegram_chat_id = "111"
    dept_head_user.telegram_chat_id = "222"
    db.commit()

    assert [u.id for u in notification_service.edu_department_recipients(db)] == [edu_department_user.id]
    assert [u.id for u in notification_service.dept_heads_with_telegram(db)] == [dept_head_user.id]
