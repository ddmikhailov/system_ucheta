import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Слабые/дефолтные секреты, с которыми запуск считается небезопасным (см.
# TODO.md 1.6): если JWT_SECRET не задан явно или совпадает с одним из этих
# значений — токен администратора можно подделать, зная только эту строку
# из публичного репозитория.
_INSECURE_JWT_SECRETS = {
    "change-me-in-production",
    "change-me",
    "secret",
    "test",
}


# Длинные, но узнаваемые заготовки («change-me-to-a-long-random-string») и строки из пары символов
# проходили проверку длины; случайный секрет их не содержит.
_PLACEHOLDER_WORDS = ("change", "default", "example", "placeholder", "password", "secret", "qwerty", "12345")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Цифровой куратор"
    # По умолчанию — "production" (fail-safe): если забыть выставить
    # переменную окружения на проде, Swagger/OpenAPI останутся выключены,
    # а не наоборот. Для локальной разработки задайте ENVIRONMENT=development
    # в backend/.env (см. .env.example).
    environment: str = "production"

    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "kait20"
    db_password: str = "kait20"
    db_name: str = "kait20"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    cors_origins: list[str] = ["http://localhost:5173"]

    # Сколько обратных прокси стоит перед приложением (обычно один). Из
    # X-Forwarded-For берётся адрес, добавленный ближайшим доверенным прокси,
    # т.е. N-й с конца: левые записи клиент может подделать (см. rate_limit.py).
    trusted_proxy_count: int = 1

    # Группа риска: студент, у которого посещаемость с начала семестра ниже порога, %. Считаются все пропуски
    # (и по уважительной причине), как в «Витринах»; сданные группой дни. Пока сдано меньше `risk_min_days` дней,
    # процент ещё случаен (один пропуск в первую неделю — это 80 %), и в риск никто не попадает.
    risk_attendance_percent: float = 85.0
    risk_min_days: int = 5

    # Блокировка подбора пароля: не учётной записи, а адреса (связка «IP + логин»)
    max_failed_login_attempts: int = 5
    lockout_minutes: int = 15
    # Для admin, edu_department, dept_head, tutor: меньше попыток и вдвое дольше пауза (тоже по адресу, не по учётке)
    max_failed_login_attempts_privileged: int = 3

    # Часовой пояс колледжа: по нему считаются «сегодня» (можно ли править
    # день, сдан ли вовремя) и время сдачи в разборе дисциплины.
    notification_timezone: str = "Europe/Moscow"

    # Мониторинг ошибок (см. TODO.md 5) — без DSN просто выключен, ничего
    # не отправляется и не падает: раньше 500-ки видел только тот, кто сам
    # догадался посмотреть логи сервера. Завести проект на sentry.io и
    # прописать DSN сюда — отдельное организационное решение, не код.
    sentry_dsn: str = ""

    # Ключ Fernet (urlsafe base64, 32 байта) для шифрования особых полей досье
    # (здоровье, соц. статус, учёт ПДН/КДН — спецкатегории по 152-ФЗ). Отдельный
    # от JWT_SECRET: ротация JWT-секрета не должна делать данные нечитаемыми.
    # Без ключа особые поля недоступны (чтение и запись), остальное работает.
    # Сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    dossier_encryption_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


def validate_jwt_secret(secret: str) -> None:
    lowered = secret.lower()
    looks_like_placeholder = any(word in lowered for word in _PLACEHOLDER_WORDS) or len(set(secret)) < 8
    if len(secret) < 32 or lowered in _INSECURE_JWT_SECRETS or looks_like_placeholder:
        raise RuntimeError(
            "JWT_SECRET не задан или слишком короткий/предсказуемый (нужна случайная строка "
            "не короче 32 символов) — иначе токен администратора можно подделать. "
            "Задайте переменную окружения JWT_SECRET."
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # PYTEST_SKIP_SECRET_CHECK — только если сознательно нужно собрать
    # Settings со слабым секретом (см. test_todo_security_fixes.py, который
    # проверяет validate_jwt_secret() напрямую и его не использует).
    if not os.environ.get("PYTEST_SKIP_SECRET_CHECK"):
        validate_jwt_secret(settings.jwt_secret)
    return settings
