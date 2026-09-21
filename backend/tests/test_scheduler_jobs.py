import datetime

import pytest

from app.core.security import hash_password
from app.models import Role, RoleCode, User
from scheduler import jobs

pytestmark = pytest.mark.asyncio

MONDAY = datetime.date(2026, 9, 21)  # реальный учебный день
SATURDAY = datetime.date(2026, 9, 26)


class FakeBot:
    """Подменяет aiogram.Bot — просто запоминает, что было бы отправлено."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


@pytest.fixture()
def fake_bot():
    return FakeBot()


async def test_reminders_sent_only_to_linked_unsubmitted_curator(imported, db, curator_group, curator_user, fake_bot):
    curator_user.telegram_chat_id = "555"
    db.commit()

    await jobs.send_first_reminder(fake_bot, today=MONDAY)

    assert len(fake_bot.sent) >= 1
    sent_to_curator = [m for m in fake_bot.sent if m["chat_id"] == "555"]
    assert len(sent_to_curator) == 1
    assert curator_group.code in sent_to_curator[0]["text"]
    assert sent_to_curator[0]["reply_markup"] is not None


async def test_reminder_not_resent_if_already_notified_today(imported, db, curator_group, curator_user, fake_bot):
    curator_user.telegram_chat_id = "555"
    db.commit()

    await jobs.send_first_reminder(fake_bot, today=MONDAY)
    first_count = len(fake_bot.sent)
    assert first_count >= 1

    await jobs.send_first_reminder(fake_bot, today=MONDAY)
    assert len(fake_bot.sent) == first_count  # второй прогон ничего не добавил


async def test_reminder_skips_submitted_group(imported, db, curator_group, curator_user, fake_bot):
    from app.services import attendance_service

    curator_user.telegram_chat_id = "555"
    db.commit()

    attendance_service.submit_day(db, curator_group.id, MONDAY, [], curator_user, today=MONDAY)

    await jobs.send_first_reminder(fake_bot, today=MONDAY)
    assert not any(m["chat_id"] == "555" for m in fake_bot.sent)


async def test_dept_head_digest_lists_unsubmitted_groups(imported, db, dept_head_user, curator_group, fake_bot):
    dept_head_user.telegram_chat_id = "777"
    db.commit()

    await jobs.send_dept_head_digest(fake_bot, today=MONDAY)

    sent = [m for m in fake_bot.sent if m["chat_id"] == "777"]
    assert len(sent) == 1
    assert curator_group.code in sent[0]["text"]


async def test_edu_department_digest_reports_college_summary(imported, db, edu_department_user, fake_bot):
    edu_department_user.telegram_chat_id = "888"
    db.commit()

    await jobs.send_edu_department_digest(fake_bot, today=MONDAY)

    sent = [m for m in fake_bot.sent if m["chat_id"] == "888"]
    assert len(sent) == 1
    assert "Сдано 0 из 44" in sent[0]["text"]


async def test_leadership_digest_only_to_flagged_users(imported, db, fake_bot):
    admin = db.query(User).filter(User.username == "admin").one()
    admin.telegram_chat_id = "999"
    admin.receives_leadership_digest = True
    db.commit()

    await jobs.send_leadership_digest(fake_bot, today=MONDAY)

    sent = [m for m in fake_bot.sent if m["chat_id"] == "999"]
    assert len(sent) == 1
    assert "Недельный дайджест" in sent[0]["text"]


async def test_no_reminders_sent_on_weekend(imported, db, curator_group, curator_user, fake_bot):
    curator_user.telegram_chat_id = "555"
    db.commit()

    await jobs.send_first_reminder(fake_bot, today=SATURDAY)
    assert fake_bot.sent == []


async def test_deputy_receives_reminder_instead_of_curator(imported, db, curator_group, curator_user, fake_bot):
    from app.models import AssignmentRole, CuratorAssignment

    deputy_role = db.query(Role).filter(Role.code == RoleCode.DEPUTY_CURATOR.value).one()
    deputy = User(
        username="deputy_test", full_name="Заместитель", role_id=deputy_role.id,
        password_hash=hash_password("x"), telegram_chat_id="333",
    )
    db.add(deputy)
    db.commit()

    db.add(
        CuratorAssignment(
            study_group_id=curator_group.id, user_id=deputy.id, role_type=AssignmentRole.DEPUTY,
            start_date=MONDAY, end_date=MONDAY + datetime.timedelta(days=4),
        )
    )
    curator_user.telegram_chat_id = "555"
    db.commit()

    await jobs.send_first_reminder(fake_bot, today=MONDAY)

    assert any(m["chat_id"] == "333" for m in fake_bot.sent)
    assert not any(m["chat_id"] == "555" for m in fake_bot.sent)
