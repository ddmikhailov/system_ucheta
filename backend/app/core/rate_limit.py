"""Простой rate limit по IP в памяти процесса — без внешних зависимостей
(Redis и т.п. не нужны: приложение работает одним процессом uvicorn, см.
scripts/entrypoint.py). Раньше вход не был ограничен по IP вообще: счётчик
неудачных попыток был только per-account и сбрасывался при блокировке,
поэтому можно было перебирать пароли к множеству разных логинов
бесконечно (password spraying) — см. TODO.md 2."""
import time
from collections import defaultdict, deque

from app.core.config import get_settings

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
    """Каждый доверенный прокси дописывает в X-Forwarded-For адрес того, от кого
    получил запрос, поэтому доверять можно только записям справа: N-я с конца
    (N = TRUSTED_PROXY_COUNT) — реальный клиент. Левые записи клиент задаёт
    сам — раньше бралась первая, и лимит входа обходился подменой заголовка.
    Если заголовка нет или он короче — IP транспортного соединения."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        count = get_settings().trusted_proxy_count
        if count > 0 and len(hops) >= count:
            return hops[-count]
    return request.client.host if request.client else "unknown"
