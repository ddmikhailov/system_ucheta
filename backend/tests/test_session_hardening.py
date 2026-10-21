"""Внешний аудит 07.10.2026: HSTS, сессия в HttpOnly-cookie вместо localStorage, серверный выход, усиленный CSP."""
import datetime

from app.core.config import get_settings

settings = get_settings()
COOKIE = settings.session_cookie_name
CSRF = {"X-Requested-With": "kait20"}


def _login(client, password="GlavTest#58x!"):
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
    r = client.post("/auth/change-password", cookies={COOKIE: token}, json={"current_password": "x", "new_password": "Saffron#58xQ"})
    assert r.status_code == 403
    # Bearer-запросы (скрипты) заголовка не требуют — cookie там не участвует.
    r = client.post("/auth/change-password", headers=admin_headers, json={"current_password": "wrong", "new_password": "Saffron#58xQ"})
    assert r.status_code == 400


def test_logout_ends_only_this_browser(client, admin_headers):
    """«Выйти» стирает cookie этого браузера, но не выкидывает с других устройств (раньше выход
    увеличивал версию токенов, и человека разлогинивало и на телефоне)."""
    phone = _login(client).json()["access_token"]
    laptop = _login(client).json()["access_token"]
    client.cookies.clear()

    r = client.post("/auth/logout", cookies={COOKIE: laptop}, headers=CSRF)
    assert r.status_code == 204
    assert COOKIE in r.headers["set-cookie"]  # cookie стирается
    assert client.get("/auth/me", cookies={COOKIE: phone}).status_code == 200


def test_logout_all_revokes_every_session(client, admin_headers):
    phone = _login(client).json()["access_token"]
    laptop = _login(client).json()["access_token"]
    client.cookies.clear()

    r = client.post("/auth/logout-all", cookies={COOKIE: laptop}, headers=CSRF)
    assert r.status_code == 204
    assert COOKIE in r.headers["set-cookie"]
    # Сессия на другом устройстве и украденная копия токена больше не работают.
    assert client.get("/auth/me", cookies={COOKIE: phone}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {laptop}"}).status_code == 401


def test_logout_all_requires_session_and_csrf_header(client, admin_headers):
    assert client.post("/auth/logout-all").status_code == 401
    token = _login(client).json()["access_token"]
    client.cookies.clear()
    assert client.post("/auth/logout-all", cookies={COOKIE: token}).status_code == 403
    assert client.get("/auth/me", cookies={COOKIE: token}).status_code == 200  # сессия не тронута


def test_logout_all_allowed_with_pending_password_change(client, db, admin_headers):
    from app.models import User

    admin = db.query(User).filter(User.username == "admin").one()
    admin.must_change_password = True
    db.commit()
    assert client.post("/auth/logout-all", headers=admin_headers).status_code == 204


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
    r = client.post("/auth/change-password", headers=admin_headers, json={"current_password": "GlavTest#58x!", "new_password": "Pebble#58xQ"})
    assert r.status_code == 200 and COOKIE in r.headers["set-cookie"]


def test_cookie_secure_follows_environment_unless_overridden():
    from app.core.config import Settings

    assert Settings(environment="production", jwt_secret="x" * 40).cookie_secure is True
    assert Settings(environment="development", jwt_secret="x" * 40).cookie_secure is False
    # явное отключение — для временной работы по http без сертификата
    assert Settings(environment="production", jwt_secret="x" * 40, session_cookie_secure=False).cookie_secure is False


_ADMIN_ID = 1  # admin — единственный пользователь в сидах


def _token(auth_time: datetime.datetime, minutes: int) -> str:
    """Токен администратора из сидов, выданный с заданным временем ввода пароля и сроком."""
    from app.core.security import create_access_token

    original = settings.access_token_expire_minutes
    settings.access_token_expire_minutes = minutes
    try:
        return create_access_token(_ADMIN_ID, "admin", 0, auth_time)
    finally:
        settings.access_token_expire_minutes = original


def _cookie_token(response) -> str | None:
    cookie = response.headers.get("set-cookie", "")
    if not cookie.startswith(f"{COOKIE}="):
        return None
    return cookie.split(";", 1)[0].split("=", 1)[1]


def test_fresh_session_is_not_renewed(client, seeded):
    token = _token(datetime.datetime.now(datetime.UTC), 12 * 60)
    r = client.get("/auth/me", cookies={COOKIE: token})
    assert r.status_code == 200 and _cookie_token(r) is None


def test_session_near_expiry_is_renewed_with_same_auth_time(client, seeded):
    """Кто работает, не вылетает через 12 часов: /auth/me выдаёт новый cookie ещё на полный срок."""
    from app.core.security import decode_access_token

    entered = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=11)
    token = _token(entered, 60)  # до конца час — меньше порога продления
    r = client.get("/auth/me", cookies={COOKIE: token})
    assert r.status_code == 200
    renewed = _cookie_token(r)
    assert renewed and renewed != token
    payload = decode_access_token(renewed)
    assert payload["auth_time"] == int(entered.timestamp())
    lifetime = payload["exp"] - datetime.datetime.now(datetime.UTC).timestamp()
    assert lifetime > settings.access_token_expire_minutes * 60 - 60
    assert "Max-Age" in r.headers["set-cookie"]
    assert client.get("/auth/me", cookies={COOKIE: renewed}).status_code == 200


def test_renewal_never_passes_the_overall_limit(client, seeded):
    from app.core.security import decode_access_token

    limit = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=3)
    entered = limit - datetime.timedelta(days=settings.session_max_days)
    token = _token(entered, 60)  # до общего предела 3 часа: новый токен — только до него, а не на 12 часов
    renewed = _cookie_token(client.get("/auth/me", cookies={COOKIE: token}))
    assert renewed and decode_access_token(renewed)["exp"] == int(limit.timestamp())


def test_session_at_overall_limit_is_not_renewed(client, seeded):
    limit = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)
    entered = limit - datetime.timedelta(days=settings.session_max_days)
    token = _token(entered, 60)  # срок уже упёрся в предел: exp = auth_time + session_max_days
    r = client.get("/auth/me", cookies={COOKIE: token})
    assert r.status_code == 200 and _cookie_token(r) is None


def test_bearer_token_is_not_renewed(client, seeded):
    entered = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=11)
    token = _token(entered, 60)
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and _cookie_token(r) is None


def test_old_token_without_auth_time_is_renewed_from_issue_time(client, seeded):
    """Токены, выданные до продления сессий, не несут auth_time — отсчёт общего предела от их выдачи."""
    import jwt

    from app.core.security import decode_access_token

    now = datetime.datetime.now(datetime.UTC)
    issued = now - datetime.timedelta(hours=11)
    token = jwt.encode(
        {"sub": str(_ADMIN_ID), "role": "admin", "tv": 0, "iat": issued, "exp": now + datetime.timedelta(minutes=30)},
        settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    renewed = _cookie_token(client.get("/auth/me", cookies={COOKIE: token}))
    assert renewed and decode_access_token(renewed)["auth_time"] == int(issued.timestamp())
