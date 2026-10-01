# КАИТ-20 — установка на сервер

В архиве две папки: `backend/` (Python) и `frontend/` (исходники интерфейса на React).
Собранный интерфейс уже лежит в `backend/static`, поэтому **Node.js на сервере не нужен** —
он требуется только если вы захотите пересобрать интерфейс сами.

Проверьте целостность архива: SHA-256 должен совпасть с файлом `.sha256` рядом с ним.

## 1. Что установить заранее

| Что | Версия | Зачем |
|---|---|---|
| Python | **3.14** (строго 3.14.x) | запуск приложения; на другой версии оно откажется стартовать |
| MySQL | 8.4, кодировка `utf8mb4`, сортировка `utf8mb4_unicode_ci` | база данных |
| Шрифт DejaVu Sans (Linux: пакет `fonts-dejavu-core`) | любая | кириллица в PDF-выгрузках; без него PDF строятся, но кириллица в них нечитаема. На Windows используется системный Arial |
| Обратный прокси с HTTPS (nginx, Caddy и т. п.) | любой | платформа сама HTTPS не обслуживает |

Исходящий доступ в интернет приложению не нужен (кроме опционального Sentry, если задан `SENTRY_DSN`).
Компилятор не нужен: все пакеты ставятся готовыми колёсами.

## 2. База данных

```sql
CREATE DATABASE kait20 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kait20'@'localhost' IDENTIFIED BY '<пароль>';
GRANT ALL PRIVILEGES ON kait20.* TO 'kait20'@'localhost';
```

Таблицы создаются автоматически при первом запуске (миграции).

## 3. Установка

```bash
cd backend
python3.14 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.txt     # Windows: .venv\Scripts\pip ...
cp .env.example .env                                           # и заполните, см. ниже
```

`requirements.txt` — полный список пакетов с точными версиями и хэшами; один файл для Linux и Windows.

## 4. Настройка (`backend/.env`)

Обязательно: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `JWT_SECRET`
(длинная случайная строка), `ADMIN_USERNAME`, `ADMIN_PASSWORD` (пароль первого администратора;
при первом входе его сменят). Остальные параметры описаны в `.env.example`.
Переменные окружения, заданные в системе, важнее значений из `.env`.

Дополнительно для запуска:

- `PORT` — порт (по умолчанию 8000);
- `HOST` — адрес прослушивания (по умолчанию `0.0.0.0`; если прокси на том же сервере — поставьте `127.0.0.1`);
- `TRUSTED_PROXY_COUNT` — сколько прокси стоит перед приложением (обычно 1), иначе лимит попыток входа
  будет считать всех пользователей одним адресом;
- `IMPORT_ON_START=true` — один раз импортировать данные «Диджитал» из `backend/scripts/import/data`
  (после первого раза выключите).

## 5. Запуск

```bash
cd backend
.venv/bin/python -m scripts.entrypoint
```

Скрипт сам: дожидается базы → применяет миграции → создаёт справочники и администратора →
запускает приложение. Проверка: `http://<сервер>:8000/health` отвечает 200, главная страница — интерфейс.

**Запускайте ровно один экземпляр приложения.** Лимит попыток входа хранится в памяти процесса;
несколько экземпляров будут считать его раздельно.

Для постоянной работы запустите команду как службу (systemd, Windows-служба и т. п.) с рабочей
папкой `backend`. Ниже — шаблон для systemd; **он не проверялся на реальном сервере**, адаптируйте под себя:

```ini
[Unit]
Description=KAIT-20
After=network.target mysql.service

[Service]
WorkingDirectory=/opt/kait20/backend
ExecStart=/opt/kait20/backend/.venv/bin/python -m scripts.entrypoint
Restart=on-failure
User=kait20

[Install]
WantedBy=multi-user.target
```

Запуск проверен: Linux (Python 3.14, чистая установка по `requirements.txt` с хэшами, MySQL 8.4) и Windows.
Не проверялись: оформление в службу (systemd/Windows), ARM, macOS.

## 6. Обновление версии

Остановите приложение, замените содержимое `backend/` (сохранив `.env` и `.venv`), выполните
`pip install --require-hashes -r requirements.txt`, запустите заново — миграции применятся сами.
Перед обновлением сделайте резервную копию БД (`mysqldump`).

## 7. Пересборка интерфейса (необязательно)

Нужны Node.js 22.12+ и npm. В папке `frontend`: `npm ci && npm run build`, затем содержимое
`frontend/dist` скопируйте в `backend/static`.
