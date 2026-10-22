"""«Восстановить пароль»: запрос с экрана входа, уведомления тем, кто вправе выдать пароль, закрытие запроса;
воспитательный отдел привязан к отделению и выдаёт пароли только в нём."""
import pytest

from app.core.security import hash_password
from app.models import Department, InAppNotification, PasswordResetRequest, Role, RoleCode, User


def _curator(db):
    role = db.query(Role).filter(Role.code == "curator").one()
    return db.query(User).filter(User.role_id == role.id).first()


def _make_user(db, username, role_code, department_id, password="Zebra#58xQz1"):
    role = db.query(Role).filter(Role.code == role_code).one()
    user = User(username=username, full_name=f"Тест {username}", role_id=role.id, department_id=department_id,
                password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _notified_ids(db):
    return {n.user_id for n in db.query(InAppNotification).filter(InAppNotification.kind == "password_reset")}


@pytest.fixture()
def other_department(db, seeded):
    dept = Department(name="Другое отделение")
    db.add(dept)
    db.commit()
    return dept


def test_unknown_login_gets_the_same_neutral_answer(client, db, imported):
    known = client.post("/auth/forgot-password", json={"username": _curator(db).username})
    unknown = client.post("/auth/forgot-password", json={"username": "no_such_login"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert db.query(PasswordResetRequest).count() == 1


def test_request_notifies_everyone_who_can_issue_the_password(
    client, db, imported, admin_headers, dept_head_user, edu_department_user, other_department
):
    target = _curator(db)
    tutor = _make_user(db, "tutor1", "tutor", target.department_id)
    foreign_head = _make_user(db, "head_other", "dept_head", other_department.id)
    foreign_edu = _make_user(db, "edu_other", "edu_department", other_department.id)
    curator_mate = _make_user(db, "mate_curator_x", "curator", target.department_id)
    admin = db.query(User).filter(User.username == "admin").one()

    assert client.post("/auth/forgot-password", json={"username": target.username}).status_code == 202

    ids = _notified_ids(db)
    assert ids == {admin.id, dept_head_user.id, tutor.id, edu_department_user.id}
    assert not ids & {foreign_head.id, foreign_edu.id, curator_mate.id, target.id}
    note = db.query(InAppNotification).filter(InAppNotification.user_id == dept_head_user.id).one()
    assert target.full_name in note.message
    assert note.entity_type == "password_reset" and note.entity_id == str(target.id)


def test_department_head_forgetting_password_goes_to_admin_only(client, db, dept_head_user, edu_department_user):
    admin = db.query(User).filter(User.username == "admin").one()
    client.post("/auth/forgot-password", json={"username": dept_head_user.username})
    assert _notified_ids(db) == {admin.id}


def test_repeated_request_does_not_duplicate_notifications(client, db, imported, dept_head_user):
    username = _curator(db).username
    client.post("/auth/forgot-password", json={"username": username})
    count = db.query(InAppNotification).filter(InAppNotification.kind == "password_reset").count()
    client.post("/auth/forgot-password", json={"username": username})
    assert db.query(InAppNotification).filter(InAppNotification.kind == "password_reset").count() == count
    assert db.query(PasswordResetRequest).count() == 1


def test_issuing_password_closes_request_and_clears_other_notifications(
    client, db, imported, dept_head_headers, edu_department_user, edu_department_headers
):
    target = _curator(db)
    client.post("/auth/forgot-password", json={"username": target.username})

    r = client.post(f"/admin/users/{target.id}/set-password", headers=edu_department_headers, json={})
    assert r.status_code == 200
    temp = r.json()["password"]

    request = db.query(PasswordResetRequest).one()
    assert request.status == "done" and request.resolved_by == edu_department_user.id
    db.expire_all()
    assert all(n.read_at is not None for n in db.query(InAppNotification).filter(InAppNotification.kind == "password_reset"))
    assert client.post("/auth/login", json={"username": target.username, "password": temp}).status_code == 200


def test_edu_department_issues_passwords_only_in_own_department(
    client, db, imported, edu_department_user, edu_department_headers, other_department, admin_headers
):
    outsider = _make_user(db, "far_curator", "curator", other_department.id)
    r = client.post(f"/admin/users/{outsider.id}/set-password", headers=edu_department_headers, json={})
    assert r.status_code == 403

    head = _make_user(db, "own_head", "dept_head", edu_department_user.department_id)
    assert client.post(f"/admin/users/{head.id}/set-password", headers=edu_department_headers, json={}).status_code == 403

    own = _curator(db)
    assert client.post(f"/admin/users/{own.id}/set-password", headers=edu_department_headers, json={}).status_code == 200


def test_edu_department_cannot_edit_block_or_delete_accounts(client, db, imported, edu_department_headers):
    """Воспитательный отдел в своём отделении только выдаёт пароли: учётки кураторов не правит и не удаляет."""
    own = _curator(db)
    assert client.patch(f"/admin/users/{own.id}", headers=edu_department_headers, json={"full_name": "Другое Имя"}).status_code == 403
    assert client.patch(f"/admin/users/{own.id}", headers=edu_department_headers, json={"is_active": False}).status_code == 403
    assert client.delete(f"/admin/users/{own.id}", headers=edu_department_headers).status_code == 403
    db.refresh(own)
    assert own.is_active and own.full_name != "Другое Имя"


def test_edu_department_is_attached_to_a_department_and_sees_only_it(
    client, db, imported, edu_department_user, edu_department_headers, other_department
):
    _make_user(db, "far_curator", "curator", other_department.id)
    rows = client.get("/admin/users", headers=edu_department_headers).json()
    assert rows and {u["department_id"] for u in rows} == {edu_department_user.department_id}


def test_admin_can_attach_edu_department_to_department(client, db, seeded, admin_headers, other_department):
    created = client.post("/admin/users", headers=admin_headers, json={
        "full_name": "Специалист ВР", "username": "vr_spec", "role": RoleCode.EDU_DEPARTMENT.value,
        "department_id": other_department.id,
    })
    assert created.status_code == 201
    assert created.json()["department_id"] == other_department.id


def test_forgot_password_is_rate_limited(client, db, imported):
    codes = [client.post("/auth/forgot-password", json={"username": f"x{i}"}).status_code for i in range(7)]
    assert codes[:5] == [202] * 5 and codes[5] == 429
