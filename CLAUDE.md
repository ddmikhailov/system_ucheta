# КАИТ-20 — платформа-помощник куратора

Учёт посещаемости (ядро) + досье студента + задачи от администрации + индивидуальная работа + соц. паспорт.
Единое приложение: FastAPI отдаёт и API, и собранный React (`frontend/dist` → `backend/static`).

## Правила работы (обязательно)

- **Публикация — только по явной команде пользователя.** `git push` (он же редеплой на Amvera, если это `main`),
  деплой и коммиты — только когда пользователь прямо попросил (с релиза 2.0 запрет на push снят: хук больше не блокирует).
- **Отчёты — по-русски**: после крупного действия и в конце работы. Код, имена и коммиты — как в окружающем коде
  (комментарии и тексты интерфейса — на русском).
- **Только синтетические данные.** Реальные ФИО/ПДн в разработке, тестах и примерах не использовать.
  `backend/scripts/import/data/*.csv|xlsx` — реальные данные, вне git; не читать и не показывать.
- Секреты (`.env`, `DOSSIER_ENCRYPTION_KEY`, `JWT_SECRET`) не печатать и не править.

## Команды

```bash
# backend (из backend/)
python -m pytest -q                   # весь набор (SQLite); TEST_DATABASE_URL=mysql+pymysql://... — на MySQL
python -m pytest tests/test_tasks.py -q
alembic upgrade head                  # миграции
alembic revision -m "..."             # новая миграция (цепочку head проверить: alembic heads — одна голова)

# frontend (из frontend/)
npm test                              # Vitest, однократно
npm run build                         # tsc -b && vite build
npx oxlint                            # линтер
```

Dev-сервер фронтенда — `.claude/launch.json` (имя `frontend`, порт 5173). Python 3.14, Node ≥ 22.

## Архитектура backend (`backend/app`)

- `api/routers/*` — тонкие эндпоинты; `api/routers/admin/` — пакет по областям.
- `services/*` — бизнес-логика (`task_service`, `attendance_service`, `individual_work_service`, `passport_service` …).
  Сервисы **не импортируют из `app.api`**.
- `core/policies.py` — единое место проверок доступа; `core/roles.py` — группы ролей; `services/access_service.py`.
- `models/*`, `schemas/*`; миграции — `backend/alembic/versions` (на каждый этап — своя).
- Особые поля досье (здоровье, соц. статус, учёт) шифруются (`core/field_crypto.py`); просмотр пишется в журнал.
- Время — только `today_local()` / `utcnow()` из `core/time.py`. Excel-ячейки с текстом пользователя — через
  `core/xlsx.append_row` (защита от формул).
- Планировщика нет: напоминания и периодические задачи срабатывают при открытии платформы. Один процесс uvicorn.

## Frontend (`frontend/src`)

React 19 + React Router 7 + Vite 8, без UI-библиотек и без state-менеджера. `constants/roles.ts` — зеркало
`app/core/roles.py` (контрактный тест `tests/test_frontend_roles_contract.py` сверяет их: **менять роли в обоих местах**).
Даты — только `utils/date.ts` (`formatDateRu`). Мобильная ширина (375 px) — обязательная проверка для нового UI.

## Роли

`curator`, `deputy_curator`, `dept_head`, `edu_department`, `admin`, `tutor`, `social_pedagogue`, `psychologist`.
Куратор видит только свои группы; зав. отделением и тьютор — своё отделение; `edu_department`, админ,
соц. педагог, психолог — весь колледж. Любой новый эндпоинт: ролевая зависимость **или** проверка доступа к объекту
внутри; новый срез прав — строка в `tests/test_policies_matrix.py`.

## Как оформлять этап

1. Миграция + модель + сервис + роутер + схемы; тесты backend (роль × действие) и frontend (Vitest).
2. Запись в `CHANGELOG.md` («Не выпущено», стиль — подробный абзац на русском), решения — в `futures.md`
   (раздел «Ход этапа N»), хвосты — в `TODO.md` (раздел 6, чекбоксы).
3. Проверить в браузере на десктопе и 375 px; `npm run build` и `oxlint` без замечаний.

## Известные грабли

- Тесты зависят от дня недели: отметки ставят только в учебные дни — использовать фикстуру `today`.
- Ответ собирать **до** `commit()` (после коммита объекты устаревают → лишние запросы); списки — через `joinedload`.
- Lock-файлы `requirements*.txt` и `package-lock.json` руками не править (генерируются; CI это проверяет).
- Каталог `.claude/` в `.gitignore` — настройки Claude Code локальные.
