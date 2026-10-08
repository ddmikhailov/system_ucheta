import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import admin, attendance_changes, auth, curator, dashboards, dossier, dossier_import, export, individual_work, my_day, notifications, passport, students, tasks, events, meetings, reports, my_id, meals
from app.core.config import get_settings
from app.core.observability import init_sentry
from app.core.rate_limit import client_ip
from app.core.request_context import set_client_ip

logging.basicConfig(level=logging.INFO)
settings = get_settings()
init_sentry(settings)

# Сюда кладётся собранный фронтенд (frontend/dist → backend/static). В
# локальной разработке (frontend — отдельный `npm run dev` на 5173) этой папки
# нет, и весь блок ниже просто не активируется.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# Swagger/OpenAPI отдаёт полную карту API (роли, поля, эндпоинты) кому
# угодно без авторизации — открываем их только в явной локальной разработке,
# по умолчанию (в т.ч. если ENVIRONMENT забыли выставить в проде) считаем
# небезопасным и отключаем (см. TODO.md 0).
_docs_enabled = settings.environment == "development"
app = FastAPI(
    title=settings.app_name,
    # Держим в паре с "version" в frontend/package.json и backend/pyproject.toml —
    # единого источника правды нет (backend и frontend собираются раздельно,
    # общий VERSION-файл сюда не даёт выигрыша, см. TODO.md 5), поэтому при
    # бампе версии меняйте все три места;
    # tests/test_versions.py проверяет, что они не разошлись.
    version="3.3.0",
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
    # IP запроса — в contextvar, чтобы log_action() мог его подставить в
    # audit_log без изменения сигнатуры два десятка вызовов в роутерах
    # (см. TODO.md 5: ip_address раньше нигде не заполнялся).
    set_client_ip(client_ip(request))
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    # За обратным прокси приложение видит запрос как http (TLS завершает прокси), поэтому
    # схему запроса проверять нельзя — раньше заголовок из-за этого не отправлялся вовсе.
    # Браузеры игнорируют HSTS в ответах по http, так что отправлять его всегда безопасно.
    # includeSubDomains не ставим: домен принадлежит хостингу, поддомены — не наши.
    if get_settings().environment != "development":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
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
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response

app.include_router(auth.router)
app.include_router(curator.router)
app.include_router(attendance_changes.router)
app.include_router(dashboards.router)
app.include_router(admin.router)
app.include_router(export.router)
app.include_router(notifications.router)
app.include_router(students.router)
app.include_router(dossier.router)
app.include_router(events.router)
app.include_router(meetings.router)
app.include_router(reports.router)
app.include_router(my_id.router)
app.include_router(dossier_import.router)
app.include_router(individual_work.router)
app.include_router(my_day.router)
app.include_router(passport.router)
app.include_router(tasks.router)
app.include_router(meals.router)


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


class _ImmutableStaticFiles(StaticFiles):
    """Файлы в /assets у Vite именованы с хэшем содержимого — при изменении
    контента меняется и имя файла, так что старую версию можно кэшировать
    вечно (см. TODO.md 5: без этого CDN/браузер мог держать index.html без
    Cache-Control и после деплоя ссылаться на уже удалённые ассеты)."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# Пути, которые браузер открывает «как страницу», но которые принадлежат серверу, а не интерфейсу.
_SERVER_ONLY_PREFIXES = ("/assets", "/docs", "/redoc", "/openapi.json", "/health")


def is_browser_navigation(method: str, path: str, headers) -> bool:
    """Человек открыл адрес в браузере (обновил страницу, перешёл по закладке или ссылке), а не
    интерфейс запросил данные. Нужно, потому что адреса интерфейса («/my-day», «/tasks», «/students»…)
    совпадают с адресами API: без этой проверки F5 на них показывал JSON «Нужна авторизация»."""
    if method not in ("GET", "HEAD") or path.startswith(_SERVER_ONLY_PREFIXES):
        return False
    destination = headers.get("sec-fetch-dest")  # современные браузеры: «document» для страниц, «empty» для fetch
    if destination is not None:
        return destination == "document"
    return "text/html" in headers.get("accept", "")


def register_spa(application: FastAPI, static_dir: Path) -> None:
    """Подключает собранный интерфейс: /assets, отдачу страниц при переходе по адресу и SPA-фоллбэк."""
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", _ImmutableStaticFiles(directory=assets_dir), name="assets")

    # Переход по адресу в браузере — всегда страница интерфейса, даже если такой же адрес есть у API.
    # Запросы самого интерфейса (fetch) идут с другим заголовком и попадают в API как обычно.
    @application.middleware("http")
    async def serve_page_on_navigation(request, call_next):
        if is_browser_navigation(request.method, request.url.path, request.headers):
            return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})
        return await call_next(request)

    # SPA-фоллбэк: отдаём реальный файл, если он есть (favicon, лого,
    # манифест), иначе index.html — дальше маршрутизацией занимается
    # React Router на клиенте. Регистрируется последним, поэтому не
    # перехватывает уже объявленные выше API-маршруты.
    #
    # index.html (и прочие файлы вне /assets) — без долгого кэша: иначе
    # браузер после деплоя может взять старую версию, ссылающуюся на уже
    # удалённые ассеты, и получить белый экран (см. TODO.md 5).
    @application.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = resolve_static_file(full_path, static_dir)
        segments = full_path.split("/")
        if candidate is None and ("." in segments[-1] or any(seg.startswith(".") for seg in segments)):
            # Маршруты SPA без расширения и точки в начале; запрос вида /.env, /.git/HEAD, /x.map — это поиск
            # файла, и честный 404 лучше «200 с главной страницей» (так сканеры и мониторинг
            # не принимают отсутствующий файл за существующий).
            raise HTTPException(status_code=404, detail="Not Found")
        target = candidate if candidate is not None else static_dir / "index.html"
        return FileResponse(target, headers={"Cache-Control": "no-cache"})


if STATIC_DIR.is_dir():
    register_spa(app, STATIC_DIR)
