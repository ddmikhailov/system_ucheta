from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Пул побольше стандартного (5 + 10): на сервере запросы идут параллельно из многих вкладок (колокольчик опрашивает
# сервер сам), и пока один тяжёлый запрос держит соединение, остальные ждут — при исчерпании пула все они падали
# по таймауту через 30 с (QueuePool limit reached).
engine = create_engine(
    settings.database_url, pool_pre_ping=True, pool_recycle=3600,
    pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass
