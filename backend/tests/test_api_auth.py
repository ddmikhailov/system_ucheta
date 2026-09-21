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


def test_invitation_preview_and_accept(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    target = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.post(f"/admin/users/{target.id}/invitations", headers=admin_headers)
    assert r.status_code == 200
    token = r.json()["token"]

    r = client.get(f"/auth/invitations/{token}")
    assert r.status_code == 200
    assert r.json()["full_name"] == target.full_name

    r = client.post(f"/auth/invitations/{token}/accept", json={"password": "NewPass123!"})
    assert r.status_code == 200
    access_token = r.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 200
    assert r.json()["id"] == target.id

    # Ссылкой нельзя воспользоваться повторно.
    r = client.post(f"/auth/invitations/{token}/accept", json={"password": "AnotherPass123!"})
    assert r.status_code == 400


def test_invitation_unknown_token(client, seeded):
    r = client.get("/auth/invitations/does-not-exist")
    assert r.status_code == 404
