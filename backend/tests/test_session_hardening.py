"""Внешний аудит 07.10.2026: HSTS, сессия в HttpOnly-cookie вместо localStorage, серверный выход, усиленный CSP."""
from app.core.config import get_settings

settings = get_settings()
COOKIE = settings.session_cookie_name
CSRF = {"X-Requested-With": "kait20"}


def _login(client, password="AdminTest123!"):
    return client.post("/auth/login", json={"username": "admin", "password": password})


def test_hsts_is_sent_behind_a_tls_terminating_proxy(client, seeded):
    """За прокси приложение видит http; заголовок раньше из-за этого не отправлялся (SEC-01)."""
    r = client.get("/health")
    assert r.headers["strict-transport-security"] == "max-age=31536000"


def test_csp_forbids_plugins_base_and_foreign_forms(client, seeded):
    csp = client.get("/health").headers["content-security-policy"]
    for part in ("object-src 'none'", "base-uri 'self'", "form-action 'self'", "script-src 'self'"):
        assert part in csp


def test_login_sets_httponly_strict_cookie(client, admin_headers):
    r = _login(client)
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" in cookie


def test_cookie_authenticates_safe_requests(client, admin_headers):
    token = _login(client).json()["access_token"]
    client.cookies.clear()
    r = client.get("/auth/me", cookies={COOKIE: token})
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_cookie_auth_requires_csrf_header_on_changes(client, admin_headers):
    token = _login(client).json()["access_token"]
    client.cookies.clear()
    r = client.post("/auth/change-password", cookies={COOKIE: token}, json={"current_password": "x", "new_password": "Whatever12345"})
    assert r.status_code == 403
    # Bearer-запросы (скрипты) заголовка не требуют — cookie там не участвует.
    r = client.post("/auth/change-password", headers=admin_headers, json={"current_password": "wrong", "new_password": "Whatever12345"})
    assert r.status_code == 400


def test_logout_revokes_the_token_on_the_server(client, admin_headers):
    token = _login(client).json()["access_token"]
    client.cookies.clear()
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    r = client.post("/auth/logout", cookies={COOKIE: token}, headers=CSRF)
    assert r.status_code == 204
    assert COOKIE in r.headers["set-cookie"]  # cookie стирается

    # Украденная копия токена после выхода больше не работает.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_logout_without_session_is_harmless(client, seeded):
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout", headers={"Authorization": "Bearer garbage"}).status_code == 204


def test_logout_via_cookie_without_csrf_header_is_rejected(client, admin_headers):
    token = _login(client).json()["access_token"]
    client.cookies.clear()
    assert client.post("/auth/logout", cookies={COOKIE: token}).status_code == 403
    assert client.get("/auth/me", cookies={COOKIE: token}).status_code == 200  # сессия не тронута


def test_blocked_login_tells_when_to_retry(client, admin_headers):
    for _ in range(settings.max_failed_login_attempts_privileged):
        _login(client, "wrong")
    r = _login(client)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_change_password_refreshes_the_session_cookie(client, admin_headers):
    r = client.post("/auth/change-password", headers=admin_headers, json={"current_password": "AdminTest123!", "new_password": "NewAdminPass123!"})
    assert r.status_code == 200 and COOKIE in r.headers["set-cookie"]
