# Релиз 3.5.0 — выключаемые модули: план реализации

> **Для исполнителя:** superpowers:executing-plans (выбрано пользователем: «составляй план и выполняй» — исполнение в этой сессии, без субагентов). Шаги — чекбоксы.

**Цель:** оставить в платформе посещаемость, задачи, «Мой ID», питание; остальное скрыть переменной `ENABLED_MODULES`, не удаляя код и данные.

**Архитектура:** реестр модулей в `app/core/modules.py` читает `Settings.enabled_modules`; `main.py` подключает роутеры выключенных модулей не по умолчанию (404); сквозные связи закрываются проверкой `module_enabled(...)` в сервисах; `/auth/me` отдаёт `modules`, фронтенд фильтрует меню, маршруты и вкладки через `isModuleOn(user, name)`.

**Стек:** FastAPI, SQLAlchemy, pytest; React 19, React Router 7, Vitest.

**Спецификация:** `docs/superpowers/specs/2026-10-12-release-modules-design.md`

## Глобальные ограничения

- Имена модулей: `attendance` (всегда включён), `tasks`, `my_id`, `meals`, `dossier`, `passport`, `individual_work`, `plan`, `meetings`, `reports`; значение `all` включает всё.
- Значение по умолчанию: `attendance,tasks,my_id,meals`. Неизвестное имя — `RuntimeError` при запуске.
- Python — не новее 3.12 по синтаксису; комментарии и тексты интерфейса — по-русски; даты — через `utils/date.ts`.
- Роли менять нельзя (`core/roles.py` ↔ `constants/roles.ts`). Миграций нет. Данные и шифрование не трогаем.
- Lock-файлы руками не править (`package-lock.json` — `npm install --package-lock-only`).
- Коммиты/push — по команде пользователя: он дал её для этого релиза («запушь версию в github»); Amvera не проверять.
- Реальных ФИО в тестах/примерах нет.

## Review Focus

- Выключенный модуль доступен по прямой ссылке или по ссылке из старой закладки `?tab=passport` → редирект/«Журнал», не пустая страница.
- Старая задача с привязкой поля к досье в релизе: ответ принимается, ничего не пишется в досье, форма открывается без предзаполнения.
- «Мой день» у куратора без индивидуальной работы и дней рождения не падает на пустых полях.
- `ENABLED_MODULES` с пробелами/регистром/пустой строкой: `" Tasks , MEALS "` работает; пустая строка = релизный набор; опечатка → ошибка.
- Все эндпоинты выключенных модулей, включая «Список группы» и «Личные карточки» (`/curator/.../roster-sheet`, `/cards`), недоступны всем ролям.

---

### Task 1: Реестр модулей и настройка

**Files:** Create `backend/app/core/modules.py`; Modify `backend/app/core/config.py`, `backend/tests/conftest.py`, `backend/.env.example`; Test `backend/tests/test_modules.py`.

**Interfaces — Produces:**
- `ALL_MODULES: tuple[str, ...]`, `RELEASE_MODULES: tuple[str, ...] = ("attendance","tasks","my_id","meals")`
- `parse_modules(raw: str) -> frozenset[str]` — нормализует (strip, lower), пусто → релизный набор, `all` → все, `attendance` добавляется всегда, неизвестное → `RuntimeError`.
- `enabled_modules() -> frozenset[str]` (из `get_settings().enabled_modules`, вызывается каждый раз — тесты подменяют поле), `module_enabled(name: str) -> bool`.
- `Settings.enabled_modules: str = ""`.

- [ ] Тесты `test_modules.py`: `parse_modules("")`→релизный набор; `parse_modules(" Tasks , MEALS ")`→`{attendance,tasks,meals}`; `parse_modules("all")`→все десять; `parse_modules("tasks,passprt")` → `RuntimeError` с именем опечатки; `module_enabled("attendance")` истинно даже при `enabled_modules="meals"`.
- [ ] Запустить — падают (модуля нет).
- [ ] Реализовать `modules.py`; в `Settings` добавить поле; в `get_settings()` вызвать `parse_modules(settings.enabled_modules)` для ранней проверки опечатки.
- [ ] `conftest.py`: до импорта `app.*` — `os.environ.setdefault("ENABLED_MODULES", "all")` (существующие тесты проверяют полный набор).
- [ ] `.env.example`: блок `ENABLED_MODULES` с описанием и релизным значением по умолчанию.
- [ ] `python -m pytest tests/test_modules.py -q` — зелёный.

### Task 2: Подключение роутеров, `require_module`, документы куратора, `/auth/me`

**Files:** Modify `backend/app/main.py`, `backend/app/api/deps.py`, `backend/app/api/routers/curator.py`, `backend/app/api/routers/auth.py`, `backend/app/schemas/auth.py`; Test `backend/tests/test_release_modules.py`.

**Interfaces — Produces:** `main.include_module_routers(app: FastAPI, modules: frozenset[str]) -> None`; `deps.require_module(name: str)` — зависимость, 404 «Раздел отключён» при выключенном модуле; `MeResponse.modules: list[str]` (отсортирован).
Карта роутер → модуль: `dossier`,`dossier_import`→`dossier`; `passport`→`passport`; `individual_work`→`individual_work`; `events`→`plan`; `meetings`→`meetings`; `reports`→`reports`; `my_id`→`my_id`; `meals`→`meals`; `tasks`→`tasks`; остальные — всегда.

- [ ] Тесты: на свежем `FastAPI()` с `include_module_routers(app, parse_modules(""))` каждый путь роутеров выключенных модулей (берётся из `router.routes`) → 404 на `TestClient` (без авторизации — именно 404, а не 401); пути включённых модулей → не 404. `GET /curator/groups/1/roster-sheet?fields=full_name` и `/cards?fields=full_name` под администратором в релизном режиме (`monkeypatch.setattr(get_settings(), "enabled_modules", "")`) → 404; под `all` — как раньше. `/auth/me` содержит `modules == ["attendance","meals","my_id","tasks"]` в релизе и все десять под `all`; то же для `POST /auth/change-password`.
- [ ] Реализовать: вынести подключение роутеров в `include_module_routers`; `main.py` вызывает с `enabled_modules()`. `curator.roster_sheet` и `curator.group_cards` — `dependencies=[Depends(require_module("dossier"))]`. `/auth/me` и `/auth/change-password` заполняют `modules` (общий помощник в `auth.py`).
- [ ] Запустить `tests/test_release_modules.py`, затем весь `python -m pytest -q` — зелёный (режим `all` из conftest).

### Task 3: Сквозные связи в сервисах

**Files:** Modify `backend/app/api/routers/tasks.py`, `backend/app/services/task_service.py`, `backend/app/services/task_dossier.py` (только точки вызова), `backend/app/services/my_day_service.py`; Test `backend/tests/test_release_modules.py` (дополнить), при необходимости `tests/test_my_day.py`.

- [ ] Тесты (релизный режим через `monkeypatch.setattr(get_settings(), "enabled_modules", "")`): `GET /tasks/dossier-fields` → `200 []`; создание задачи с `dossier_field` → 422 «Привязка к досье недоступна»; принятие ответа по задаче, созданной в режиме `all` с привязкой, не создаёт/не меняет `StudentProfile` и не падает; `generate_followup_reminders` не вызывается (напоминания по индивидуальной работе не создаются); `GET /my-day` у куратора: `attention == []`, `attention_total == 0`, `birthdays == []`, остальное на месте; под `all` — прежнее поведение (существующие тесты).
- [ ] Реализовать условия `module_enabled("dossier")` / `module_enabled("individual_work")`: `tasks.dossier_fields`, `task_service` на строках создания/валидации (`validate_links`), двух вызовов `apply_accepted`, предзаполнения (`task_dossier.prefill`, где вызывается) и `generate_followup_reminders`; `my_day_service.day_attention` (пустой результат), `day_birthdays` (пустой), `no_work_days` оставить значением константы.
- [ ] Прогнать `python -m pytest -q` в обоих режимах: `ENABLED_MODULES=all` (по умолчанию) и релизном (`ENABLED_MODULES=` пусто; ожидаемо падают только тесты скрытых модулей — они помечаются `pytestmark`-пропуском «модуль выключен» через общую фикстуру/маркер `needs_module`, добавленную в conftest).
- [ ] Вывод: в релизном прогоне пропущены только тесты выключенных модулей, остальное зелёное.

### Task 4: Frontend — инфраструктура и навигация

**Files:** Create `frontend/src/constants/modules.ts`, `frontend/src/utils/modules.ts`, `frontend/src/utils/modules.test.ts`; Modify `frontend/src/api/types.ts` (`MeResponse.modules: string[]`), `Layout.tsx`, `App.tsx`, `CommandPalette.tsx` (если собирает пункты сам), `frontend/src/test/*` (заглушка пользователя с `modules`), `backend/tests/test_frontend_roles_contract.py` (сверка списка `MODULES` с `core/modules.py`).

**Interfaces — Produces:** `MODULE = { ATTENDANCE, TASKS, MY_ID, MEALS, DOSSIER, PASSPORT, INDIVIDUAL_WORK, PLAN, MEETINGS, REPORTS }` (строки как у backend); `isModuleOn(user: MeResponse | null, name: string): boolean` (нет пользователя → `false`; нет поля `modules` → `true`).

- [ ] Тесты: `isModuleOn` (включён/выключен/нет поля/нет пользователя); `Layout.test.tsx` — куратор и админ в релизе не видят «Соц. паспорт», «Индивидуальная работа», «План группы», «Отчёт куратора», видят «Мой ID», «Питание», «Задачи»; `App.test.tsx` — `/passport`, `/individual-work`, `/plan`, `/report` при релизном `modules` редиректят на `/`; контрактный тест сверяет имена.
- [ ] Реализовать: `Layout.navItems` — пункты по `isModuleOn`; `/my-id` и `/meals`, `/tasks`, `/my-tasks`, `/tasks/assignment/*` — тоже по модулям `my_id`/`meals`/`tasks`; `App.tsx` — обёртка `RequireModule` (`Navigate to="/"`), `/students/:id` остаётся.
- [ ] `npm test`, `npx oxlint` — зелёные.

### Task 5: Frontend — вкладки, карточка студента, «Мой день», задачи

**Files:** Modify `pages/CuratorGroupPage.tsx`, `components/DayJournal.tsx` (кнопки «Список группы», «Личные карточки»), `pages/StudentCardPage.tsx`, `pages/MyDayPage.tsx`, `components/TaskCreateForm.tsx`, `pages/StudentsSearchPage.tsx` (скрыть `DossierImport`), `pages/UserProfilePage.tsx` (скрыть «Просмотров досье» и записи работы), `pages/AdminPage.tsx`/`admin/*` при ссылках на досье; соответствующие `*.test.tsx`.

- [ ] Тесты (Vitest, `modules` релизного набора): вкладки группы = «Журнал», «Студенты», «Питание», «Мой ID»; `?tab=passport` открывает «Журнал»; карточка студента: вкладки «Обзор», «Посещаемость», «История», «Управление» (последняя — как раньше по роли), нет KPI «Записи работы»/«Вернуться к вопросу» и нет запроса `/students/{id}/dossier` (`useDossier` не вызывается); «Мой день» без блока «внимание» и кнопки «Записать»; `TaskCreateForm` без выбора «досье» и без запроса `/tasks/dossier-fields`; `StudentsSearchPage` без импорта досье; `DayJournal` без кнопок документов.
- [ ] Реализовать фильтрацию по `isModuleOn`; хук `useDossier` вызывается условно (не трогать правила хуков: вынести загрузку во вложенный компонент или передавать `enabled`).
- [ ] `npm test`, `npm run build`, `npx oxlint` — без замечаний.

### Task 6: Версия и документы разработки

**Files:** Modify `backend/app/main.py` (`version="3.5.0"`), `backend/pyproject.toml`, `frontend/package.json`, `frontend/package-lock.json` (через `npm install --package-lock-only`), `CHANGELOG.md`, `futures.md`, `plan-v2.md`, `TODO.md`, `README.md` (если описывает разделы).

- [ ] `tests/test_versions.py` падает на старых версиях → бамп → зелёный.
- [ ] `CHANGELOG.md`: подробный абзац «Релиз 3.5.0» (набор модулей, `ENABLED_MODULES`, что скрыто и почему, ограничения: индивидуальный признак «договор» студента нельзя править без досье; данные остаются в базе). `futures.md`: решение о правах/данных. `plan-v2.md`: «вернуть скрытые модули». `TODO.md` раздел 6: хвосты (удаление данных досье — отдельное решение; проверка 152-ФЗ для хранения скрытых данных).

### Task 7: Проверка

- [ ] `cd backend && python -m pytest -q` (режим `all`) и с `ENABLED_MODULES=` (релиз): первый — всё зелёное, второй — только пропуски тестов выключенных модулей.
- [ ] `cd frontend && npm test && npm run build && npx oxlint` — без замечаний.
- [ ] Браузер (`preview_start frontend` + backend в релизном режиме): вход под куратором и администратором, меню, вкладки группы, карточка студента, «Мой день» — десктоп и 375 px; скриншоты как подтверждение.

### Task 8: Инструкция администратору, архив, публикация

**Files:** Modify `docs/install-guide.md`, `docs/deploy/README.txt` (если упоминает состав), `tools/build_deploy_pdf.py` (текст PDF), пересобранные `docs/deploy/*.pdf`; Create (вне git) `release/kait20-3.5.0.zip`, `.sha256`, `release/kait20-3.5.0-INSTALL.md`.

- [ ] `install-guide.md`: раздел 4 — `ENABLED_MODULES` (релизное значение по умолчанию, `all`, как вернуть модули, перезапуск службы), примечание про `DOSSIER_ENCRYPTION_KEY` (ключ хранить, хотя досье скрыто); раздел проверки после установки — вход и список разделов меню. Те же изменения в тексте `tools/build_deploy_pdf.py`.
- [ ] `python tools/build_deploy_pdf.py` — PDF пересобраны; `python tools/build_release.py` — архив `release/kait20-3.5.0.zip` + `.sha256`; проверка состава архива (самопроверка инструмента и `tests/test_release_tool.py`).
- [ ] `git status`/`git diff --stat` — только ожидаемые файлы; коммит с русским сообщением («Релиз 3.5.0: …») и подписью соавтора; `git push` в `origin main`. Amvera не проверяется.
