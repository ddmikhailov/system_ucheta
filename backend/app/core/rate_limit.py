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


# Неудачные входы по связке «IP + логин» — отдельно от общего лимита по IP.
# Блокируется не учётная запись (иначе любой, кто знает логин, мог бы закрыть
# её владельцу вход подбором паролей), а тот адрес, с которого идёт подбор.
_failures: dict[str, deque[float]] = defaultdict(deque)
_FAILURES_PRUNE_AT = 10_000  # ключи берутся из ввода клиента — держим словарь ограниченным


def _prune(bucket: deque[float], now: float, window_seconds: int) -> None:
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()


def is_blocked(key: str, max_failures: int, window_seconds: int) -> bool:
    bucket = _failures.get(key)
    if bucket is None:
        return False
    _prune(bucket, time.monotonic(), window_seconds)
    if not bucket:
        del _failures[key]
        return False
    return len(bucket) >= max_failures


def register_failure(key: str, window_seconds: int) -> int:
    """Записывает неудачную попытку и возвращает их число в окне."""
    now = time.monotonic()
    if len(_failures) >= _FAILURES_PRUNE_AT:
        for k in list(_failures):
            _prune(_failures[k], now, window_seconds)
            if not _failures[k]:
                del _failures[k]
    bucket = _failures[key]
    _prune(bucket, now, window_seconds)
    bucket.append(now)
    return len(bucket)


def reset_failures(key: str) -> None:
    _failures.pop(key, None)


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
