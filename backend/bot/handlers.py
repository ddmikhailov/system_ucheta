import datetime
import logging

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from app.api.deps import get_curator_group_ids
from app.db.base import SessionLocal
from app.models import StudyGroup, User
from app.services import attendance_service
from app.services.telegram_link_service import ChatAlreadyLinked, LinkTokenInvalid, consume_link_token
from bot import messages

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    token = command.args
    if not token:
        await message.answer(messages.start_welcome_no_payload())
        return

    db = SessionLocal()
    try:
        user = consume_link_token(db, token, str(message.chat.id))
        await message.answer(messages.link_success(user.full_name))
    except LinkTokenInvalid:
        await message.answer(messages.link_invalid())
    except ChatAlreadyLinked:
        await message.answer(messages.link_chat_taken())
    finally:
        db.close()


@router.callback_query(F.data.startswith("allpresent:"))
async def handle_all_present(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        return
    _, group_id_raw, date_raw = callback.data.split(":")
    group_id = int(group_id_raw)
    date = datetime.date.fromisoformat(date_raw)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_chat_id == str(callback.from_user.id)).one_or_none()
        if user is None:
            await callback.answer("Аккаунт не привязан.", show_alert=True)
            return

        if group_id not in get_curator_group_ids(db, user, date):
            await callback.answer("Это не ваша группа.", show_alert=True)
            return

        group = db.get(StudyGroup, group_id)
        if group is None:
            await callback.answer("Группа не найдена.", show_alert=True)
            return

        try:
            attendance_service.submit_day(db, group_id, date, [], user, today=datetime.date.today())
        except attendance_service.BackdateNotAllowed as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        confirmation_text = messages.submit_confirmed(group.code, date)
    finally:
        db.close()

    await callback.answer("Готово!")
    if callback.message is not None:
        await callback.message.answer(confirmation_text)
