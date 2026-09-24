"""Простой rate limit по IP в памяти процесса — без внешних зависимостей
(Redis и т.п. не нужны: приложение работает одним процессом uvicorn, см.
docker-entrypoint.sh). Раньше вход не был ограничен по IP вообще: счётчик
неудачных попыток был только per-account и сбрасывался при блокировке,
поэтому можно было перебирать пароли к множеству разных логинов
бесконечно (password spraying) — см. TODO.md 2."""
import time
from collections import defaultdict, deque

_attempts: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """Возвращает False, если лимит уже превышен. Иначе регистрирует эту
    попытку и возвращает True."""
    now = time.monotonic()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= max_attempts:
        return False
    bucket.append(now)
    return True


def client_ip(request) -> str:
    """Amvera (и любой другой обратный прокси перед приложением) — единственный
    путь снаружи, поэтому первому IP из X-Forwarded-For можно доверять
    настолько же, насколько самому прокси; если заголовка нет — берём IP
    транспортного соединения напрямую."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
