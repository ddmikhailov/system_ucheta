import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import get_settings
from app.models import StudyGroup

settings = get_settings()


def reminder_keyboard(groups: list[StudyGroup], date: datetime.date) -> InlineKeyboardMarkup:
    rows = []
    for group in groups:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✓ {group.code}: все присутствуют",
                    callback_data=f"allpresent:{group.id}:{date.isoformat()}",
                ),
                InlineKeyboardButton(
                    text="Открыть",
                    url=f"{settings.web_app_base_url}/cabinet?group={group.id}&date={date.isoformat()}",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
