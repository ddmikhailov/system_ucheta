"""Обновление 1.2: роль tutor (полный доступ по колледжу, как admin) и
возможность менять роль пользователя — с ограничением, кто какие роли
может назначать."""
from app.core.security import hash_password


def _make_tutor(db, client):
    from app.models import Role, User

    role = db.query(Role).filter(Role.code == "tutor").one()
    user = User(username="tutor1", full_name="Тьютор Тьюторович", role_id=role.id, password_hash=hash_password("TutorPass1"))
    db.add(user)
    db.commit()
    r = client.post("/auth/login", json={"username": "tutor1", "password": "TutorPass1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_tutor_has_full_college_access(client, imported, db):
    tutor_headers = _make_tutor(db, client)

    r = client.get("/admin/groups", headers=tutor_headers)
    assert r.status_code == 200
    assert len(r.json()) == 44  # весь колледж, не одно отделение

    r = client.get("/admin/users", headers=tutor_headers)
    assert r.status_code == 200

    # Может создавать группы (раньше — только admin).
    from app.models import Department

    dept = db.query(Department).one()
    r = client.post(
        "/admin/groups", headers=tutor_headers,
        json={"code": "TUTOR_TEST", "course": 1, "department_id": dept.id, "study_form": None},
    )
    assert r.status_code == 201, r.text


def test_tutor_can_access_any_group_journal(client, imported, db):
    from app.models import StudyGroup

    tutor_headers = _make_tutor(db, client)
    group = db.query(StudyGroup).first()
    r = client.get(f"/curator/groups/{group.id}/day?date=2026-09-01", headers=tutor_headers)
    assert r.status_code == 200


def test_admin_can_change_curator_role_to_dept_head(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=admin_headers, json={"role": "dept_head"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "dept_head"


def test_admin_can_promote_to_tutor(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=admin_headers, json={"role": "tutor"})
    assert r.status_code == 200
    assert r.json()["role"] == "tutor"


def test_dept_head_cannot_promote_to_admin_or_tutor(client, dept_head_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=dept_head_headers, json={"role": "admin"})
    assert r.status_code == 403

    r = client.patch(f"/admin/users/{curator.id}", headers=dept_head_headers, json={"role": "tutor"})
    assert r.status_code == 403


def test_dept_head_can_promote_curator_to_dept_head_in_own_department(client, dept_head_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=dept_head_headers, json={"role": "dept_head"})
    assert r.status_code == 200
    assert r.json()["role"] == "dept_head"


def test_edu_department_cannot_change_roles(client, edu_department_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=edu_department_headers, json={"role": "dept_head"})
    assert r.status_code == 403


def test_cannot_change_own_role(client, admin_headers, db):
    from app.models import User

    admin = db.query(User).filter(User.username == "admin").one()
    r = client.patch(f"/admin/users/{admin.id}", headers=admin_headers, json={"role": "curator"})
    assert r.status_code == 400


def test_role_change_rejects_unknown_role(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()
    r = client.patch(f"/admin/users/{curator.id}", headers=admin_headers, json={"role": "nonexistent"})
    assert r.status_code == 400
