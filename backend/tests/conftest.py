import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.base as db_base
from app.core.security import hash_password
from app.models import (  # noqa: F401 -- регистрирует все таблицы в Base.metadata
    CuratorAssignment,
    Department,
    Role,
    RoleCode,
    StudyGroup,
    User,
)

ADMIN_PASSWORD = "AdminTest123!"
DEPT_HEAD_USERNAME = "zavotd"
DEPT_HEAD_PASSWORD = "ZavOtd123!"
CURATOR_PASSWORD = "CuratorTest123!"


@pytest.fixture()
def test_engine(tmp_path):
    """Изолированная SQLite-БД на каждый тест — никакого общего состояния между тестами."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
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
def imported(seeded, db):
    """Справочники + реальный набор «Диджитал» (44 группы, 989 студентов, 24 куратора)."""
    import scripts.import_source_data as import_script

    import_script.run()
    db.expire_all()
    return seeded


def _login(client, username: str, password: str) -> dict:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client, db, seeded):
    admin = db.query(User).filter(User.username == "admin").one()
    admin.password_hash = hash_password(ADMIN_PASSWORD)
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
    return datetime.date.today()
