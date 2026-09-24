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


def test_account_locks_after_max_failed_attempts(client, admin_headers):
    for _ in range(settings.max_failed_login_attempts):
        r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    # Даже правильный пароль теперь не проходит — учётка заблокирована.
    r = client.post("/auth/login", json={"username": "admin", "password": "AdminTest123!"})
    assert r.status_code == 423


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
