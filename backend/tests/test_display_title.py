"""«Отображаемое звание» — та же роль и права, другая подпись в интерфейсе
(например, «Советник директора по воспитанию» вместо «Зав. отделением»)."""


def test_create_user_with_display_title(client, admin_headers, db):
    from app.models import Department

    dept = db.query(Department).one()
    r = client.post(
        "/admin/users", headers=admin_headers,
        json={
            "full_name": "Иванов Иван Иванович",
            "username": "advisor_test",
            "role": "dept_head",
            "department_id": dept.id,
            "display_title": "Советник директора по воспитанию",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "dept_head"
    assert r.json()["display_title"] == "Советник директора по воспитанию"


def test_update_display_title(client, admin_headers, imported, db):
    from app.models import Department, Role, User

    dept_head_role = db.query(Role).filter(Role.code == "dept_head").one()
    existing = db.query(User).filter(User.role_id == dept_head_role.id).first()
    if existing is None:
        # В импортированных данных «Диджитал» зав. отделением не заводится
        # автоматически — создаём для теста.
        dept = db.query(Department).one()
        r = client.post(
            "/admin/users", headers=admin_headers,
            json={"full_name": "Тест Тестович", "username": "th_test", "role": "dept_head", "department_id": dept.id},
        )
        user_id = r.json()["id"]
    else:
        user_id = existing.id

    r = client.patch(f"/admin/users/{user_id}", headers=admin_headers, json={"display_title": "Советник директора по воспитанию"})
    assert r.status_code == 200
    assert r.json()["display_title"] == "Советник директора по воспитанию"

    r = client.get("/admin/users", headers=admin_headers)
    row = next(u for u in r.json() if u["id"] == user_id)
    assert row["display_title"] == "Советник директора по воспитанию"
    assert row["role"] == "dept_head"  # права/роль не изменились


def test_display_title_shows_in_me_response(client, admin_headers, db):
    from app.models import Department

    dept = db.query(Department).one()
    r = client.post(
        "/admin/users", headers=admin_headers,
        json={
            "full_name": "Михайлов Денис Дмитриевич", "username": "advisor2", "role": "dept_head",
            "department_id": dept.id, "display_title": "Советник директора по воспитанию",
        },
    )
    uid = r.json()["id"]
    client.post(f"/admin/users/{uid}/set-password", headers=admin_headers, json={"password": "AdvisorPass1"})

    r = client.post("/auth/login", json={"username": "advisor2", "password": "AdvisorPass1"})
    token = r.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["role"] == "dept_head"
    assert r.json()["display_title"] == "Советник директора по воспитанию"


def test_clearing_display_title_with_empty_string(client, admin_headers, db):
    from app.models import Department

    dept = db.query(Department).one()
    r = client.post(
        "/admin/users", headers=admin_headers,
        json={
            "full_name": "Х Х", "username": "clear_title_test", "role": "dept_head",
            "department_id": dept.id, "display_title": "Что-то",
        },
    )
    uid = r.json()["id"]

    r = client.patch(f"/admin/users/{uid}", headers=admin_headers, json={"display_title": ""})
    assert r.status_code == 200
    assert r.json()["display_title"] is None
