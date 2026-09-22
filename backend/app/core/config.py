from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "КАИТ-20 Учёт посещаемости"
    environment: str = "development"

    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "kait20"
    db_password: str = "kait20"
    db_name: str = "kait20"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_origins: list[str] = ["http://localhost:5173"]

    # Правка задним числом: сколько предыдущих учебных дней куратор может редактировать сам.
    curator_backdate_days: int = 1

    # Порог для подсветки риска: количество кодов "н" подряд.
    risk_threshold_consecutive_unexcused: int = 3

    # Блокировка входа
    max_failed_login_attempts: int = 5
    lockout_minutes: int = 15

    # --- Telegram-бот и планировщик (этап 2) ---
    # По умолчанию бот и планировщик работают внутри основного процесса
    # (asyncio-задачи в lifespan FastAPI) — одно приложение, один контейнер.
    # false — только если сознательно разносите их по отдельным процессам
    # (тогда bot/main.py и scheduler/main.py запускаются самостоятельно).
    embed_workers: bool = True
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_link_token_ttl_minutes: int = 10
    notification_timezone: str = "Europe/Moscow"
    # Публичный адрес веб-интерфейса — для кнопки «Открыть» в напоминаниях.
    web_app_base_url: str = "http://localhost:5173"

    # Время ежедневных рассылок (день недели у пятничного дайджеста фиксирован в коде).
    reminder_first_time: str = "10:00"
    reminder_second_time: str = "15:00"
    dept_head_digest_time: str = "15:30"
    edu_department_digest_time: str = "16:00"
    leadership_digest_time: str = "16:30"

    # Порог для "проблемных групп" в сводке воспитательному отделу.
    problem_group_percent_threshold: float = 90.0

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
