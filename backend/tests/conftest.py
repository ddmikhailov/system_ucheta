import datetime
import os

# Должно быть выставлено раньше первого импорта из app.* — иначе Settings()
# (через lru_cache) закэширует значение до того, как мы его зададим (см.
# TODO.md 1.6: без этого get_settings() падает на слабом секрете по умолчанию).
os.environ.setdefault("JWT_SECRET", "Tq8vXn4Lw2KzR7pYb5HdJ9cMfA3sUe6G")
# Тестовый ключ Fernet для шифрования особых полей досье (не используется нигде, кроме тестов).
os.environ.setdefault("DOSSIER_ENCRYPTION_KEY", "Zm9yLXRlc3RzLW9ubHktMzItYnl0ZXMta2V5LTAwMDA=")

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.db.base as db_base
import app.core.security as security
from app.core.security import hash_password
from app.models import (  # noqa: F401 -- регистрирует все таблицы в Base.metadata
    CuratorAssignment,
    Department,
    Role,
    RoleCode,
    StudyGroup,
    User,
)

# Облегчённый argon2 только в тестах: хеш с параметрами по умолчанию (64 МБ,
# 3 прохода) занимал 3–6 с на фикстуру. verify() берёт параметры из самого
# хеша, поэтому проверка паролей работает как в проде; боевой хешер не меняется.
security._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)

ADMIN_PASSWORD = "AdminTest123!"
DEPT_HEAD_USERNAME = "zavotd"
DEPT_HEAD_PASSWORD = "ZavOtd123!"
CURATOR_PASSWORD = "CuratorTest123!"


@pytest.fixture()
def test_engine(tmp_path):
    """Изолированная БД на каждый тест — никакого общего состояния между
    тестами. По умолчанию SQLite (быстро, без внешних сервисов); если задан
    TEST_DATABASE_URL — настоящий MySQL (см. TODO.md 5: ENUM/strict mode/
    длины строк/collation в SQLite не проверяются вообще, и тесты никогда
    не заметили бы регрессию, которая ловится только на реальной БД —
    отдельный job в CI, `ci.yml`, гоняет весь набор именно так)."""
    mysql_url = os.environ.get("TEST_DATABASE_URL")
    if mysql_url:
        # READ COMMITTED, а не дефолтный для MySQL REPEATABLE READ: тесты
        # держат одну сессию (`db`) открытой через весь тест, попеременно
        # читая напрямую и дергая эндпоинты через TestClient (у которого —
        # своя, отдельная сессия на каждый запрос). При REPEATABLE READ
        # снимок `db` фиксируется на первом запросе транзакции и не видит
        # более поздних коммитов из другой сессии, пока сама не
        # закоммитится — в проде это не проблема (сессия там живёт один
        # HTTP-запрос), а в тестах превращалось в ложные падения на ровном
        # месте (см. TODO.md 5, найдено этим самым прогоном на MySQL).
        engine = create_engine(mysql_url, pool_pre_ping=True, isolation_level="READ COMMITTED")
        db_base.engine = engine
        db_base.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        db_base.Base.metadata.drop_all(engine)
        db_base.Base.metadata.create_all(engine)
        yield engine
        db_base.Base.metadata.drop_all(engine)
        engine.dispose()
        return

    db_path = tmp_path / "test.db"
    # check_same_thread=False: синхронные эндпоинты FastAPI выполняются в пуле
    # потоков — в проде это MySQL и потоки его не смущают, но SQLite по
    # умолчанию запрещает использовать соединение не из того потока, где
    # оно создано.
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    # SQLite не проверяет внешние ключи по умолчанию — в проде (MySQL/InnoDB)
    # они enforced, и на этом строится безопасное удаление (см. admin.py:
    # DELETE .../{id} ловит IntegrityError и обезличивает вместо удаления).
    # Без этого тесты не заметили бы, если проверка вообще перестанет работать.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    db_base.engine = engine
    db_base.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_base.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(test_engine):
    session = db_base.SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Лимитер по IP (app/core/rate_limit.py) — общее состояние процесса;
    без сброса между тестами один и тот же TestClient IP ("testclient")
    накопил бы попытки входа из всех тестов подряд и словил бы 429 там, где
    тест ожидает 401/200."""
    from app.core.rate_limit import _attempts, _failures

    from app.services import task_service

    _attempts.clear()
    _failures.clear()
    task_service.reset_reminder_throttle()
    yield
    _attempts.clear()
    _failures.clear()
    task_service.reset_reminder_throttle()


@pytest.fixture()
def client(test_engine):
    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        session = db_base.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(test_engine):
    """Справочники (роли, коды отметок, отделение «Диджитал», admin) — без импорта данных."""
    import scripts.seed as seed_script

    seed_script.run()
    return test_engine


@pytest.fixture()
def imported(seeded, db, monkeypatch):
    """Справочники + синтетический набор той же формы, что реальный «Диджитал»
    (44 группы, 989 студентов, 24 куратора, 3 вакансии) — коды/курсы/кол-во
    взяты из реальной выгрузки, а ФИО целиком выдуманы (см. TODO.md 5:
    раньше тесты читали backend/scripts/import/data/*.csv с настоящими ФИО,
    которых нет в репозитории — на чистом клоне/в CI это падало)."""
    import scripts.import_source_data as import_script

    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "import")
    monkeypatch.setattr(import_script, "DATA_DIR", fixtures_dir)
    import_script.run()
    # commit(), а не только expire_all(): import_script делает всё через
    # свою собственную сессию. Если что-то через `db` уже читало раньше
    # (например, dept_head_user/edu_department_user — pytest не гарантирует
    # порядок независимых фикстур), на MySQL с REPEATABLE READ у `db` уже
    # открыта транзакция со снимком ДО импорта, и expire_all() внутри неё
    # не поможет — снимок не обновляется, пока транзакция не завершится
    # (см. TODO.md 5, найдено прогоном тестов на настоящем MySQL).
    db.commit()
    return seeded


def _login(client, username: str, password: str) -> dict:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client, db, seeded):
    admin = db.query(User).filter(User.username == "admin").one()
    admin.password_hash = hash_password(ADMIN_PASSWORD)
    # seed.py принудительно требует смену пароля при первом входе (см.
    # TODO.md 0/2) — для тестов админ уже "прошёл" эту смену.
    admin.must_change_password = False
    db.commit()
    return _login(client, "admin", ADMIN_PASSWORD)


@pytest.fixture()
def dept_head_user(db, seeded):
    role = db.query(Role).filter(Role.code == RoleCode.DEPT_HEAD.value).one()
    dept = db.query(Department).one()
    user = User(
        username=DEPT_HEAD_USERNAME,
        full_name="Зав. Отделением Диджитал",
        role_id=role.id,
        department_id=dept.id,
        password_hash=hash_password(DEPT_HEAD_PASSWORD),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def dept_head_headers(client, dept_head_user):
    return _login(client, DEPT_HEAD_USERNAME, DEPT_HEAD_PASSWORD)


@pytest.fixture()
def edu_department_user(db, seeded):
    role = db.query(Role).filter(Role.code == RoleCode.EDU_DEPARTMENT.value).one()
    user = User(
        username="vospitatel",
        full_name="Воспитательный отдел",
        role_id=role.id,
        password_hash=hash_password("VospOtdel123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def edu_department_headers(client, edu_department_user):
    return _login(client, "vospitatel", "VospOtdel123!")


@pytest.fixture()
def curator_user(db, imported):
    """Первый куратор из импортированного набора «Диджитал», с заданным паролем."""
    role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one()
    user = db.query(User).filter(User.role_id == role.id).order_by(User.id).first()
    user.password_hash = hash_password(CURATOR_PASSWORD)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def curator_headers(client, curator_user):
    return _login(client, curator_user.username, CURATOR_PASSWORD)


@pytest.fixture()
def db_second_curator(db, imported, curator_user):
    """Второй куратор из импортированного набора — для сценариев "два разных аккаунта"."""
    role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one()
    user = (
        db.query(User)
        .filter(User.role_id == role.id, User.id != curator_user.id)
        .order_by(User.id)
        .first()
    )
    user.password_hash = hash_password("SecondCurator123!")
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def curator_group(db, curator_user):
    assignment = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.user_id == curator_user.id)
        .first()
    )
    return db.query(StudyGroup).filter(StudyGroup.id == assignment.study_group_id).one()


@pytest.fixture()
def today() -> datetime.date:
    # Приложение теперь везде считает "сегодня" по NOTIFICATION_TIMEZONE, а не
    # по времени сервера (см. TODO.md 3) — тесты должны сверяться с тем же
    # понятием "сегодня", иначе изредка расходились бы около полуночи UTC.
    from app.core.time import today_local

    # Отметки посещаемости ставят только в учебные дни, а набор тестов должен проходить в любой
    # день недели: по выходным (в воскресенье падали 10 тестов) берём ближайший прошедший будний.
    day = today_local()
    while day.weekday() >= 5:
        day -= datetime.timedelta(days=1)
    return day


MEAL_MANAGER_PASSWORD = "MealManager123!"


@pytest.fixture()
def meal_manager_user(db, seeded):
    role = db.query(Role).filter(Role.code == RoleCode.MEAL_MANAGER.value).one()
    user = User(
        username="pitanie", full_name="Ответственная по питанию", role_id=role.id,
        password_hash=hash_password(MEAL_MANAGER_PASSWORD),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def meal_manager_headers(client, meal_manager_user):
    return _login(client, meal_manager_user.username, MEAL_MANAGER_PASSWORD)
