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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
