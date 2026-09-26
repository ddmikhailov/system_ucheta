"""IP текущего запроса, доступный без протаскивания `Request` через каждую
функцию до `log_action` (см. TODO.md 5: `audit_log.ip_address` раньше нигде
не заполнялся — добавлять параметр в 20+ сигнатур роутеров ради одного поля
было бы куда инвазивнее, чем один contextvar + одна строка в middleware)."""
from contextvars import ContextVar

_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)


def set_client_ip(ip: str | None) -> None:
    _client_ip.set(ip)


def get_client_ip() -> str | None:
    return _client_ip.get()
