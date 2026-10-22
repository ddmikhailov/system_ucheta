"""Сервер для проверки мобильной вёрстки (Playwright, `npm run test:mobile`): настоящий backend на временной
базе SQLite с синтетическим набором «Диджитал» из backend/tests/fixtures (реальных ПДн нет) и собранный
интерфейс из frontend/dist. Запускается самим Playwright (webServer в playwright.config.ts).

    python e2e/server.py [порт]     # из frontend/, после npm run build
"""
import os
import sys
import tempfile
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent
BACKEND = FRONTEND.parent / "backend"
sys.path.insert(0, str(BACKEND))

# До первого импорта app.*: настройки кэшируются. Секреты — только для этой одноразовой базы.
os.environ["JWT_SECRET"] = "E2e5vXn4Lw2KzR7pYb5HdJ9cMfA3sUe6GtQm"
os.environ["DOSSIER_ENCRYPTION_KEY"] = "Zm9yLXRlc3RzLW9ubHktMzItYnl0ZXMta2V5LTAwMDA="
os.environ["ENABLED_MODULES"] = "all"
os.environ["ENVIRONMENT"] = "development"
os.environ["SESSION_COOKIE_SECURE"] = "false"
# Файл .env из backend/ не читаем: настройки берутся из каталога запуска.
os.chdir(tempfile.mkdtemp(prefix="kait20-e2e-"))

import uvicorn  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.db.base as db_base  # noqa: E402
from app.core.security import hash_password  # noqa: E402

ADMIN_PASSWORD = "Vt4#Wq8nXs2!kL"
CURATOR_USERNAME = "e2e.curator"
CURATOR_PASSWORD = "Pm6#Hy3rGc7!zN"


def prepare_database() -> None:
    engine = create_engine(f"sqlite:///{Path.cwd() / 'e2e.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    db_base.engine = engine
    db_base.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    import app.models  # noqa: F401 -- регистрирует таблицы
    import scripts.import_source_data as import_script
    import scripts.seed as seed_script

    db_base.Base.metadata.create_all(engine)
    seed_script.run()
    import_script.DATA_DIR = str(BACKEND / "tests" / "fixtures" / "import")
    import_script.run()

    from app.models import CuratorAssignment, Role, RoleCode, User

    with db_base.SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        admin.password_hash = hash_password(ADMIN_PASSWORD)
        admin.must_change_password = False
        # Куратор с самой большой группой: длинный список в журнале — главный случай для узкого экрана.
        role = db.query(Role).filter(Role.code == RoleCode.CURATOR.value).one()
        curators = db.query(User).filter(User.role_id == role.id).all()
        curator = max(curators, key=lambda u: db.query(CuratorAssignment).filter_by(user_id=u.id).count())
        curator.username = CURATOR_USERNAME
        curator.password_hash = hash_password(CURATOR_PASSWORD)
        curator.must_change_password = False
        db.commit()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4310
    prepare_database()

    from app.db.session import get_db
    from app.main import app, register_spa

    def override_get_db():
        session = db_base.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    register_spa(app, FRONTEND / "dist")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
