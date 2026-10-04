"""Роль tutor — полный доступ, но только к своему отделению; плюс
возможность менять роль пользователя — с ограничением, кто какие роли
может назначать."""
import datetime

from app.core.security import hash_password


def _make_tutor(db, client):
    from app.models import Department, Role, User

    role = db.query(Role).filter(Role.code == "tutor").one()
    user = User(
        username="tutor1", full_name="Тьютор Тьюторович", role_id=role.id,
        department_id=db.query(Department).order_by(Department.id).first().id, password_hash=hash_password("TutorPass1"),
    )
    db.add(user)
    db.commit()
    r = client.post("/auth/login", json={"username": "tutor1", "password": "TutorPass1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _other_department_group(db):
    from app.models import Department, StudyGroup

    other = Department(name="Другое отделение")
    db.add(other)
    db.flush()
    group = StudyGroup(code="OTHER-1", course=1, department_id=other.id)
    db.add(group)
    db.commit()
    return other, group


def test_tutor_has_full_access_within_own_department(client, imported, db):
    from app.models import Department, StudyGroup

    tutor_headers = _make_tutor(db, client)
    other, other_group = _other_department_group(db)
    own = db.query(Department).filter(Department.id != other.id).one()

    groups = client.get("/admin/groups", headers=tutor_headers).json()
    assert groups and {g["department_id"] for g in groups} == {own.id}  # чужого отделения не видно
    assert client.get("/admin/users", headers=tutor_headers).status_code == 200

    # Группы своего отделения — создаёт; в чужом — нет.
    r = client.post("/admin/groups", headers=tutor_headers,
                    json={"code": "TUTOR_TEST", "course": 1, "department_id": own.id, "study_form": None})
    assert r.status_code == 201, r.text
    r = client.post("/admin/groups", headers=tutor_headers,
                    json={"code": "TUTOR_TEST2", "course": 1, "department_id": other.id, "study_form": None})
    assert r.status_code == 403
    # Отделения и справочники — только администратор/воспитательный отдел.
    assert client.post("/admin/departments", headers=tutor_headers, json={"name": "Новое"}).status_code == 403
    assert client.put("/admin/calendar", headers=tutor_headers, json={}).status_code in (403, 422)

    own_group = db.query(StudyGroup).filter(StudyGroup.department_id == own.id).first()
    assert client.get(f"/curator/groups/{own_group.id}/day?date=2026-09-01", headers=tutor_headers).status_code == 200
    assert client.get(f"/curator/groups/{other_group.id}/day?date=2026-09-01", headers=tutor_headers).status_code == 403
    assert client.patch(f"/admin/groups/{other_group.id}", headers=tutor_headers, json={"is_active": False}).status_code == 403


def test_tutor_dossier_only_for_own_department_students(client, imported, db):
    from app.models import Department, Student, StudyGroup

    tutor_headers = _make_tutor(db, client)
    other, other_group = _other_department_group(db)
    foreign = Student(last_name="Чужой", first_name="С", study_group_id=other_group.id, enrolled_at=datetime.date(2026, 9, 1))
    db.add(foreign)
    db.commit()
    own = db.query(Student).filter(Student.study_group_id != other_group.id).first()

    assert client.get(f"/students/{own.id}/dossier", headers=tutor_headers).status_code == 200
    r = client.put(f"/students/{own.id}/dossier/profile", headers=tutor_headers,
                   json={"special": {"has_ovz": True}})
    assert r.status_code == 200
    assert client.get(f"/students/{foreign.id}/dossier", headers=tutor_headers).status_code == 403
    assert client.get(f"/students/{foreign.id}/dossier/access-log", headers=tutor_headers).status_code == 403
    assert client.get(f"/students/{own.id}/dossier/access-log", headers=tutor_headers).status_code == 200
    names = [r["id"] for r in client.get("/students", params={"q": "Чужой"}, headers=tutor_headers).json()]
    assert foreign.id not in names


def test_tutor_creates_staff_only_in_own_department(client, imported, db):
    from app.models import Department

    tutor_headers = _make_tutor(db, client)
    other, _ = _other_department_group(db)
    own = db.query(Department).filter(Department.id != other.id).one()
    r = client.post("/admin/users", headers=tutor_headers,
                    json={"username": "psy_t", "full_name": "Психолог", "role": "psychologist", "department_id": other.id})
    assert r.status_code == 201
    assert r.json()["department_id"] == own.id  # чужое отделение подменяется на своё
    r = client.post("/admin/users", headers=tutor_headers,
                    json={"username": "dh_t", "full_name": "Зав", "role": "dept_head"})
    assert r.status_code == 403


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


def test_tutor_cannot_change_roles(client, imported, db):
    """Тьютор может назначать только рабочие роли своего отделения, но не зав. отделением."""
    from app.models import Role, User

    tutor_headers = _make_tutor(db, client)
    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=tutor_headers, json={"role": "dept_head"})
    assert r.status_code == 403


def test_tutor_can_delete_a_group_forever_only_in_own_department(client, imported, db):
    """Тьютор — полный доступ к своему отделению, включая удаление группы с историей (с кодом подтверждения);
    чужую группу удалить нельзя. Зав. отделением удалить группу насовсем не может (см. отдельный тест)."""
    from app.models import StudyGroup

    tutor_headers = _make_tutor(db, client)
    other, other_group = _other_department_group(db)
    own_group = db.query(StudyGroup).filter(StudyGroup.id != other_group.id).first()
    own_id, own_code = own_group.id, own_group.code
    client.patch(f"/admin/groups/{own_id}", headers=tutor_headers, json={"is_active": False})

    r = client.delete(f"/admin/groups/{other_group.id}?force=true&confirm_code={other_group.code}", headers=tutor_headers)
    assert r.status_code == 403
    r = client.delete(f"/admin/groups/{own_id}?force=true&confirm_code={own_code}", headers=tutor_headers)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(StudyGroup, own_id) is None and db.get(StudyGroup, other_group.id) is not None
