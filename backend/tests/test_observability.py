"""Мониторинг ошибок (см. TODO.md 5) — без SENTRY_DSN не должен ничего
делать, а с ним — вызывать sentry_sdk.init() один раз с этим DSN."""
from app.core.config import Settings
from app.core.observability import init_sentry


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

    assert init_sentry(_settings(sentry_dsn="https://example.com/1")) is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://example.com/1"
