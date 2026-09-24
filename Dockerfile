# Единое приложение: backend (FastAPI, встроенные бот и планировщик) сам
# отдаёт собранную статику фронтенда. Один образ, один контейнер — см.
# README, раздел «Архитектура: почему единое приложение».

FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.14-slim
WORKDIR /app

# fonts-dejavu-core — чтобы кириллица корректно рендерилась в PDF-экспорте (reportlab).
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-build /frontend/dist ./static

RUN chmod +x /app/docker-entrypoint.sh

# Контейнер работал от root без необходимости (см. TODO.md 2) — /app не
# нужно ничего писать во время работы (БД внешняя, статика read-only),
# только entrypoint на старте (миграции/seed) должен успеть выполниться от
# этого же пользователя, поэтому создаём его до переключения.
RUN groupadd -r app && useradd -r -g app app
USER app

EXPOSE 8000

# start-period с запасом на миграции+справочники при первом старте контейнера.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["/app/docker-entrypoint.sh"]
