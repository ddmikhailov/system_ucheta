import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import admin, auth, curator, dashboards, export, notifications
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

# В сборке Docker сюда копируется собранный frontend/dist (см. корневой
# Dockerfile). В локальной разработке (frontend — отдельный `npm run dev`
# на 5173) этой папки нет, и весь блок ниже просто не активируется.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot: Bot | None = None
    background_tasks: list[asyncio.Task] = []
    scheduler = None

    if settings.telegram_enabled and settings.embed_workers:
        from app.worker_runtime import build_scheduler, run_bot_polling

        bot = Bot(token=settings.telegram_bot_token)
        background_tasks.append(asyncio.create_task(run_bot_polling(bot)))
        scheduler = build_scheduler(bot)
        scheduler.start()
        logger.info("Бот и планировщик запущены внутри основного процесса.")
    elif settings.telegram_enabled:
        logger.info("EMBED_WORKERS=false — бот и планировщик должны быть запущены отдельными процессами.")
    else:
        logger.info("TELEGRAM_BOT_TOKEN не задан — бот и планировщик отключены.")

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    for task in background_tasks:
        task.cancel()
    if bot is not None:
        await bot.session.close()


app = FastAPI(title=settings.app_name, version="1.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(curator.router)
app.include_router(dashboards.router)
app.include_router(admin.router)
app.include_router(export.router)
app.include_router(notifications.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if STATIC_DIR.is_dir():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA-фоллбэк: отдаём реальный файл, если он есть (favicon, лого,
    # манифест), иначе index.html — дальше маршрутизацией занимается
    # React Router на клиенте. Регистрируется последним, поэтому не
    # перехватывает уже объявленные выше API-маршруты.
    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
