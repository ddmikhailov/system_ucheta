"""Админ-панель (/admin): структура, пользователи, справочники.

Раньше — один файл на ~1000 строк; теперь по областям. Пути и поведение не менялись.
Порядок подключения важен только внутри модулей (в references: /calendar/group-overrides
объявлен раньше /calendar/{date}, иначе DELETE уходил бы не туда)."""
from fastapi import APIRouter

from app.api.routers.admin import assignments, departments, groups, references, students, users

router = APIRouter(prefix="/admin", tags=["admin"])
for _module in (departments, groups, students, references, assignments, users):
    router.include_router(_module.router)
