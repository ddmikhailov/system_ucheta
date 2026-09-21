"""Отдельный процесс для бота — на случай раздельного разворачивания.
По умолчанию бот и планировщик встроены в основной процесс приложения
(см. app.main, EMBED_WORKERS=true) — этот файл не запускается сам по себе
в стандартной конфигурации Docker Compose / Amvera.

    python -m bot.main
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot

from app.core.config import get_settings
from app.worker_runtime import run_bot_polling

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    if not settings.telegram_enabled:
        logger.error("TELEGRAM_BOT_TOKEN не задан — бот не запущен.")
        return

    bot = Bot(token=settings.telegram_bot_token)
    await run_bot_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
