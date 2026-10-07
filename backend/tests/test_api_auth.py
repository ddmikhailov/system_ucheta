from app.core.config import get_settings

settings = get_settings()


def test_login_success(client, admin_headers):
    r = client.get("/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_login_wrong_password(client, admin_headers):
    r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client, seeded):
    r = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def _login(client, password, username="admin", ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/auth/login", json={"username": username, "password": password}, headers=headers)


PRIV = settings.max_failed_login_attempts_privileged


def test_guessing_passwords_does_not_lock_the_account_owner(client, admin_headers):
    """Подбор пароля чужого логина блокирует подбирающего, а не владельца учётки."""
    for _ in range(PRIV):
        assert _login(client, "wrong", ip="203.0.113.7").status_code == 401

    # Злоумышленник с того же адреса: даже верный пароль уже не принимается.
    assert _login(client, "AdminTest123!", ip="203.0.113.7").status_code == 429
    # Владелец с другого адреса входит как обычно.
    assert _login(client, "AdminTest123!", ip="198.51.100.9").status_code == 200


def test_ordinary_account_has_the_looser_limit(client, admin_headers, imported, db):
    from app.models import User

    target = db.query(User).filter(User.role.has(code="curator")).first()
    client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "TempPassword1"})
    for _ in range(settings.max_failed_login_attempts):
        assert _login(client, "wrong", username=target.username, ip="203.0.113.7").status_code == 401
    assert _login(client, "TempPassword1", username=target.username, ip="203.0.113.7").status_code == 429
    assert _login(client, "TempPassword1", username=target.username, ip="198.51.100.9").status_code == 200


def test_privileged_account_is_guarded_stricter_and_attempt_is_audited(client, admin_headers, db):
    from app.models import AuditLog

    n = PRIV
    assert n < settings.max_failed_login_attempts
    for _ in range(n):
        assert _login(client, "wrong", ip="203.0.113.7").status_code == 401
    assert _login(client, "AdminTest123!", ip="203.0.113.7").status_code == 429
    entry = db.query(AuditLog).filter(AuditLog.action == "auth.bruteforce_blocked").one()
    assert entry.new_value == "203.0.113.7"
    # владелец с другого адреса не заблокирован
    assert _login(client, "AdminTest123!", ip="198.51.100.9").status_code == 200


def test_failures_are_counted_per_ip_and_login(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    for _ in range(PRIV):
        _login(client, "wrong", ip="203.0.113.7")
    # Другой логин с того же адреса — отдельный счётчик.
    assert _login(client, "wrong", username="nobody", ip="203.0.113.7").status_code == 401


def test_successful_login_resets_failure_counter(client, admin_headers):
    for _ in range(PRIV - 1):
        assert _login(client, "wrong").status_code == 401
    assert _login(client, "AdminTest123!").status_code == 200
    for _ in range(PRIV - 1):
        assert _login(client, "wrong").status_code == 401
    assert _login(client, "AdminTest123!").status_code == 200


def test_unknown_and_existing_login_give_identical_errors(client, admin_headers):
    """Нет разницы между «нет такого логина» и «неверный пароль» (раньше был 423)."""
    a = _login(client, "wrong", username="nobody")
    b = _login(client, "wrong")
    assert (a.status_code, a.json()) == (b.status_code, b.json()) == (401, a.json())


def test_account_is_never_locked_in_database(client, admin_headers, db):
    from app.models import User

    for _ in range(PRIV + 3):
        _login(client, "wrong")
    admin = db.query(User).filter(User.username == "admin").one()
    assert admin.locked_until is None and admin.failed_login_attempts == 0


def test_me_requires_auth(client, seeded):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_rejects_garbage_token(client, seeded):
    r = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_invitation_endpoints_removed(client, seeded):
    """Приглашения по одноразовой ссылке убраны целиком (см. TODO.md 2) —
    accept не проверял is_active, не требовал минимальную длину пароля и не
    сбрасывал must_change_password. Единственный путь выдать пароль теперь —
    POST /admin/users/{id}/set-password."""
    r = client.get("/auth/invitations/anything")
    assert r.status_code == 404
    r = client.post("/auth/invitations/anything/accept", json={"password": "whatever123"})
    assert r.status_code == 404
