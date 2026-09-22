"""М1: временные пароли от администратора вместо одноразовых ссылок."""


def _first_curator(db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    return db.query(User).filter(User.role_id == curator_role.id).first()


def test_admin_sets_temporary_password_and_curator_must_change_it(client, admin_headers, imported, db):
    target = _first_curator(db)

    r = client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == target.username
    temp_password = body["password"]
    assert len(temp_password) >= 8

    r = client.get("/admin/users", headers=admin_headers)
    row = next(u for u in r.json() if u["id"] == target.id)
    assert row["has_password"] is True
    assert row["must_change_password"] is True

    r = client.post("/auth/login", json={"username": target.username, "password": temp_password})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/auth/me", headers=headers)
    assert r.json()["must_change_password"] is True

    # Принудительная смена не требует старого пароля.
    r = client.post("/auth/change-password", headers=headers, json={"new_password": "MyOwnPass1"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False

    # Старый временный пароль больше не работает, новый — работает.
    r = client.post("/auth/login", json={"username": target.username, "password": temp_password})
    assert r.status_code == 401
    r = client.post("/auth/login", json={"username": target.username, "password": "MyOwnPass1"})
    assert r.status_code == 200


def test_admin_can_choose_password_explicitly(client, admin_headers, imported, db):
    target = _first_curator(db)
    r = client.post(
        f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "ChosenPass1"}
    )
    assert r.status_code == 200
    assert r.json()["password"] == "ChosenPass1"


def test_voluntary_password_change_requires_current_password(client, admin_headers, imported, db):
    target = _first_curator(db)
    client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "TempPass1"})

    r = client.post("/auth/login", json={"username": target.username, "password": "TempPass1"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/auth/change-password", headers=headers, json={"new_password": "FirstOwn1"})

    # Теперь пользователь сам меняет пароль по своей воле — старый обязателен.
    r = client.post("/auth/change-password", headers=headers, json={"new_password": "SecondOwn1"})
    assert r.status_code == 400

    r = client.post(
        "/auth/change-password", headers=headers,
        json={"current_password": "wrong", "new_password": "SecondOwn1"},
    )
    assert r.status_code == 400

    r = client.post(
        "/auth/change-password", headers=headers,
        json={"current_password": "FirstOwn1", "new_password": "SecondOwn1"},
    )
    assert r.status_code == 200


def test_set_password_unlocks_account(client, admin_headers, imported, db):
    from app.core.config import get_settings

    settings = get_settings()
    target = _first_curator(db)
    client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "TempPass1"})

    for _ in range(settings.max_failed_login_attempts):
        r = client.post("/auth/login", json={"username": target.username, "password": "wrong"})
        assert r.status_code == 401

    r = client.post("/auth/login", json={"username": target.username, "password": "TempPass1"})
    assert r.status_code == 423

    r = client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "NewTemp1"})
    assert r.status_code == 200

    r = client.post("/auth/login", json={"username": target.username, "password": "NewTemp1"})
    assert r.status_code == 200


def test_unlock_endpoint_without_changing_password(client, admin_headers, imported, db):
    from app.core.config import get_settings

    settings = get_settings()
    target = _first_curator(db)
    client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "TempPass1"})

    for _ in range(settings.max_failed_login_attempts):
        client.post("/auth/login", json={"username": target.username, "password": "wrong"})

    r = client.post("/auth/login", json={"username": target.username, "password": "TempPass1"})
    assert r.status_code == 423

    r = client.post(f"/admin/users/{target.id}/unlock", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["is_locked"] is False

    r = client.post("/auth/login", json={"username": target.username, "password": "TempPass1"})
    assert r.status_code == 200


def test_admin_can_edit_username_and_full_name(client, admin_headers, imported, db):
    target = _first_curator(db)
    r = client.patch(
        f"/admin/users/{target.id}", headers=admin_headers,
        json={"username": "new.login", "full_name": "Новое Имя"},
    )
    assert r.status_code == 200
    assert r.json()["username"] == "new.login"
    assert r.json()["full_name"] == "Новое Имя"


def test_cannot_rename_to_taken_username(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curators = db.query(User).filter(User.role_id == curator_role.id).limit(2).all()
    a, b = curators[0], curators[1]

    r = client.patch(f"/admin/users/{a.id}", headers=admin_headers, json={"username": b.username})
    assert r.status_code == 400


def test_dept_head_cannot_manage_user_outside_department(client, dept_head_headers, imported, db):
    from app.models import Department, Role, User

    other_dept = Department(name="Другое отделение")
    db.add(other_dept)
    db.flush()
    curator_role = db.query(Role).filter(Role.code == "curator").one()
    outsider = User(
        username="outsider.c", full_name="Чужой Куратор",
        role_id=curator_role.id, department_id=other_dept.id, password_hash=None,
    )
    db.add(outsider)
    db.commit()

    r = client.post(f"/admin/users/{outsider.id}/set-password", headers=dept_head_headers, json={})
    assert r.status_code == 403

    r = client.patch(f"/admin/users/{outsider.id}", headers=dept_head_headers, json={"full_name": "X"})
    assert r.status_code == 403


def test_dept_head_can_manage_user_inside_department(client, dept_head_headers, imported, db):
    target = _first_curator(db)
    r = client.post(f"/admin/users/{target.id}/set-password", headers=dept_head_headers, json={})
    assert r.status_code == 200
