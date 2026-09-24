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


# Swagger/OpenAPI отдаёт полную карту API (роли, поля, эндпоинты) кому
# угодно без авторизации — открываем их только в явной локальной разработке,
# по умолчанию (в т.ч. если ENVIRONMENT забыли выставить в проде) считаем
# небезопасным и отключаем (см. TODO.md 0).
_docs_enabled = settings.environment == "development"
app = FastAPI(
    title=settings.app_name,
    version="1.3.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Токен хранится в localStorage (а не в httpOnly-cookie), поэтому
    защита от кликджекинга/XSS-инъекций через заголовки особенно важна —
    раньше их не было вообще (см. TODO.md 2)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    # frame-ancestors дублирует X-Frame-Options для браузеров, которые его не
    # поддерживают; unsafe-inline для style-src — Vite инлайнит критический
    # CSS и React использует inline-стили в паре мест, ужесточать без
    # переписывания этого не имеет смысла.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self'"
    )
    return response

app.include_router(auth.router)
app.include_router(curator.router)
app.include_router(dashboards.router)
app.include_router(admin.router)
app.include_router(export.router)
app.include_router(notifications.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def resolve_static_file(requested_path: str, static_dir: Path) -> Path | None:
    """Файл, который реально можно отдать из static_dir — или None, если его
    там нет (тогда вызывающий код отдаёт index.html) либо путь пытается
    выбраться за пределы static_dir (в т.ч. через URL-кодированные "..").
    Вынесено в отдельную функцию, чтобы протестировать защиту от path
    traversal (TODO.md 1.1) без сборки фронтенда в тестовом окружении —
    маршрут ниже регистрируется только когда backend/static реально есть."""
    candidate = (static_dir / requested_path).resolve()
    if candidate.is_relative_to(static_dir.resolve()) and candidate.is_file():
        return candidate
    return None


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
        candidate = resolve_static_file(full_path, STATIC_DIR)
        if candidate is not None:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
