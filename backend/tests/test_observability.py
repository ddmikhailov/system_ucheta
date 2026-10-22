"""Мониторинг ошибок (см. TODO.md 5) — без SENTRY_DSN не должен ничего
делать, а с ним — вызывать sentry_sdk.init() один раз с этим DSN."""
from app.core.config import Settings
from app.core.observability import init_sentry, scrub_event


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret="test-secret-at-least-32-characters-long", **overrides)


def test_init_sentry_is_noop_without_dsn():
    assert init_sentry(_settings(sentry_dsn="")) is False


def test_init_sentry_calls_sentry_sdk_init_with_dsn(monkeypatch):
    calls = []

    class FakeSentrySdk:
        @staticmethod
        def init(**kwargs):
            calls.append(kwargs)

    import sys
    import types

    fake_module = types.ModuleType("sentry_sdk")
    fake_module.init = FakeSentrySdk.init
    fake_fastapi = types.ModuleType("sentry_sdk.integrations.fastapi")
    fake_fastapi.FastApiIntegration = lambda: "fastapi-integration"
    fake_starlette = types.ModuleType("sentry_sdk.integrations.starlette")
    fake_starlette.StarletteIntegration = lambda: "starlette-integration"
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_module)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.fastapi", fake_fastapi)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.starlette", fake_starlette)

    assert init_sentry(_settings(sentry_dsn="https://example.com/1"), release="3.6.0") is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://example.com/1"
    assert calls[0]["release"] == "3.6.0"
    # Без ПДн (152-ФЗ): ни тел запросов, ни cookie, ни локальных переменных в стеке.
    assert calls[0]["send_default_pii"] is False
    assert calls[0]["include_local_variables"] is False
    assert calls[0]["max_request_body_size"] == "never"
    assert calls[0]["before_send"] is scrub_event


def test_scrub_event_removes_personal_data():
    event = {
        "request": {
            "method": "POST", "url": "https://kait20.example/dossier/5",
            "data": {"full_name": "Иванов Иван"}, "cookies": {"kait20_session": "токен"},
            "headers": {"Authorization": "Bearer токен"}, "query_string": "q=Иванов",
        },
        "user": {"id": 7, "username": "ivanov", "ip_address": "10.0.0.1"},
        "breadcrumbs": {"values": [{"category": "query", "message": "SELECT 1", "data": {"params": ["Иванов"]}}]},
        "exception": {"values": [{
            "type": "IntegrityError",
            "value": "(1062, \"Duplicate entry 'Иванов Иван' for key 'students.uq'\")\n[SQL: INSERT ...]\n"
                     "[parameters: ('Иванов', 'Иван')]\n(Background on this error at: https://sqlalche.me/e/20/gkpj)",
            "stacktrace": {"frames": [{"function": "save", "vars": {"student": "Иванов Иван"}}]},
        }]},
    }
    scrubbed = scrub_event(event)
    assert scrubbed["request"] == {"method": "POST", "url": "https://kait20.example/dossier/5"}
    assert scrubbed["user"] == {"id": 7}
    assert "data" not in scrubbed["breadcrumbs"]["values"][0]
    assert "Иванов" not in str(scrubbed)
    value = scrubbed["exception"]["values"][0]["value"]
    assert "[SQL: INSERT ...]" in value and "Background on this error" in value
