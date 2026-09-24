"""Регрессионные тесты на дыры из ревью 25.09.2026 (см. TODO.md, разделы
0 и 1) — каждый тест воспроизводит ровно тот сценарий, которым уязвимость
была подтверждена, и проверяет, что теперь он блокируется."""
import datetime

from app.core.security import hash_password


def _make_user(db, role_code, username, department_id=None, password="Password123!"):
    from app.models import Role, User

    role = db.query(Role).filter(Role.code == role_code).one()
    user = User(
        username=username, full_name=username, role_id=role.id,
        department_id=department_id, password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, username, password="Password123!"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- 1.1 path traversal в SPA-фоллбэке ---


def test_resolve_static_file_blocks_path_traversal(tmp_path):
    from app.main import resolve_static_file

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("не должно быть отдано")

    assert resolve_static_file("../secret.txt", static_dir) is None
    assert resolve_static_file("..%2fsecret.txt", static_dir) is None
    assert resolve_static_file("index.html", static_dir) == (static_dir / "index.html").resolve()
    assert resolve_static_file("does-not-exist.js", static_dir) is None


# --- 1.2 воспитательный отдел не управляет учётками ---


def test_edu_department_cannot_reset_admin_password(client, admin_headers, imported, db):
    from app.models import Role, User

    edu_role = db.query(Role).filter(Role.code == "edu_department").one()
    edu_user = User(
        username="vosp_sec_test", full_name="Воспитательный отдел",
        role_id=edu_role.id, password_hash=hash_password("Password123!"),
    )
    db.add(edu_user)
    db.commit()
    edu_headers = _login(client, "vosp_sec_test")

    admin = db.query(User).filter(User.username == "admin").one()
    r = client.post(f"/admin/users/{admin.id}/set-password", headers=edu_headers, json={})
    assert r.status_code == 403

    r = client.patch(f"/admin/users/{admin.id}", headers=edu_headers, json={"full_name": "Захвачено"})
    assert r.status_code == 403


# --- 1.3 зав. отделением не может захватить/понизить старших по рангу ---


def test_dept_head_cannot_manage_tutor_admin_or_edu_department(client, dept_head_headers, imported, db):
    from app.models import User

    dept_head = db.query(User).filter(User.username == "zavotd").one()

    tutor = _make_user(db, "tutor", "tutor_sec_test", department_id=dept_head.department_id)
    admin_in_same_dept = _make_user(db, "admin", "admin_sec_test", department_id=dept_head.department_id)
    edu = _make_user(db, "edu_department", "edu_sec_test", department_id=dept_head.department_id)
    other_dept_head = _make_user(db, "dept_head", "other_zav_sec_test", department_id=dept_head.department_id)

    for target in (tutor, admin_in_same_dept, edu, other_dept_head):
        r = client.post(f"/admin/users/{target.id}/set-password", headers=dept_head_headers, json={})
        assert r.status_code == 403, f"{target.username} должен быть недоступен для dept_head"
        r = client.patch(f"/admin/users/{target.id}", headers=dept_head_headers, json={"role": "curator"})
        assert r.status_code == 403


def test_tutor_cannot_manage_other_tutor_or_admin(client, imported, db):
    from app.models import User

    tutor = _make_user(db, "tutor", "tutor_actor_sec_test")
    tutor_headers = _login(client, "tutor_actor_sec_test")

    other_tutor = _make_user(db, "tutor", "tutor_target_sec_test")
    admin = db.query(User).filter(User.username == "admin").one()

    r = client.post(f"/admin/users/{other_tutor.id}/set-password", headers=tutor_headers, json={})
    assert r.status_code == 403
    r = client.post(f"/admin/users/{admin.id}/set-password", headers=tutor_headers, json={})
    assert r.status_code == 403

    # Обычного куратора тьютор по-прежнему обслуживает.
    from app.models import Role

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()
    r = client.post(f"/admin/users/{curator.id}/set-password", headers=tutor_headers, json={})
    assert r.status_code == 200


# --- 1.4 зав. отделением без отделения не получает доступ ко всему колледжу ---


def test_dept_head_without_department_gets_403_not_full_access(client, imported, db):
    dept_head = _make_user(db, "dept_head", "no_dept_zav_sec_test", department_id=None)
    headers = _login(client, "no_dept_zav_sec_test")

    r = client.get("/admin/groups", headers=headers)
    assert r.status_code == 403

    r = client.get("/admin/users", headers=headers)
    assert r.status_code == 403

    r = client.get("/dashboards/day", headers=headers, params={"date": "2026-09-01"})
    assert r.status_code == 403


def test_create_dept_head_without_department_rejected(client, admin_headers, imported, db):
    r = client.post(
        "/admin/users", headers=admin_headers,
        json={"full_name": "Без отделения", "username": "no_dept_new", "role": "dept_head", "department_id": None},
    )
    assert r.status_code == 400


def test_create_admin_forces_no_department(client, admin_headers, imported, db):
    from app.models import Department

    dept = db.query(Department).first()
    r = client.post(
        "/admin/users", headers=admin_headers,
        json={
            "full_name": "Новый админ", "username": "new_admin_sec_test", "role": "admin",
            "department_id": dept.id,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["department_id"] is None


# --- 1.5 только admin создаёт admin/tutor ---


def test_tutor_cannot_create_admin_or_tutor_user(client, imported, db):
    tutor = _make_user(db, "tutor", "tutor_creator_sec_test")
    headers = _login(client, "tutor_creator_sec_test")

    r = client.post(
        "/admin/users", headers=headers,
        json={"full_name": "Новый админ", "username": "sneaky_admin", "role": "admin"},
    )
    assert r.status_code == 403

    r = client.post(
        "/admin/users", headers=headers,
        json={"full_name": "Новый тьютор", "username": "sneaky_tutor", "role": "tutor"},
    )
    assert r.status_code == 403


# --- 1.6 слабый JWT_SECRET не даёт стартовать ---


def test_weak_jwt_secret_is_rejected():
    import pytest

    from app.core.config import validate_jwt_secret

    for weak in ("change-me-in-production", "change-me", "secret", "short-string", ""):
        with pytest.raises(RuntimeError):
            validate_jwt_secret(weak)

    validate_jwt_secret("a-genuinely-random-string-that-is-at-least-32-chars-long")


# --- 1.8 "Все присутствуют" не должно молча стирать день ---


def test_mark_all_present_requires_confirm_when_marks_exist(client, curator_headers, curator_group, today, db):
    from app.models import MarkCode, Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    mark_code = db.query(MarkCode).filter(MarkCode.code == "н").one()

    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit",
        headers=curator_headers, params={"date": today.isoformat()},
        json={"exceptions": [{"student_id": student.id, "mark_code": mark_code.code}]},
    )
    assert r.status_code == 200

    r = client.post(
        f"/curator/groups/{curator_group.id}/day/mark-all-present",
        headers=curator_headers, params={"date": today.isoformat()},
    )
    assert r.status_code == 409

    r = client.get(f"/curator/groups/{curator_group.id}/day", headers=curator_headers, params={"date": today.isoformat()})
    entry = next(e for e in r.json()["entries"] if e["student_id"] == student.id)
    assert entry["mark_code"] == "н"

    r = client.post(
        f"/curator/groups/{curator_group.id}/day/mark-all-present",
        headers=curator_headers, params={"date": today.isoformat(), "confirm": "true"},
    )
    assert r.status_code == 200


def test_mark_all_present_no_confirm_needed_when_empty(client, curator_headers, curator_group, today):
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/mark-all-present",
        headers=curator_headers, params={"date": today.isoformat()},
    )
    assert r.status_code == 200


# --- Сессии отзываются при сбросе пароля/смене роли/архивации ---


def test_admin_password_reset_revokes_existing_session(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    target = db.query(User).filter(User.role_id == curator_role.id).first()
    target.password_hash = hash_password("OldPassword1")
    target.must_change_password = False
    db.commit()

    old_headers = _login(client, target.username, "OldPassword1")
    r = client.get("/auth/me", headers=old_headers)
    assert r.status_code == 200

    client.post(f"/admin/users/{target.id}/set-password", headers=admin_headers, json={"password": "NewPassword1"})

    r = client.get("/auth/me", headers=old_headers)
    assert r.status_code == 401


def test_self_password_change_returns_fresh_token_and_revokes_old(client, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    target = db.query(User).filter(User.role_id == curator_role.id).first()
    target.password_hash = hash_password("OldPassword1")
    target.must_change_password = False
    db.commit()

    old_headers = _login(client, target.username, "OldPassword1")

    r = client.post(
        "/auth/change-password", headers=old_headers,
        json={"current_password": "OldPassword1", "new_password": "BrandNewPass1"},
    )
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert new_token

    r = client.get("/auth/me", headers=old_headers)
    assert r.status_code == 401

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert r.status_code == 200


# --- IDOR: смена статуса чужого студента ---


def test_dept_head_cannot_change_status_of_student_outside_department(client, dept_head_headers, imported, db):
    from app.models import Department, Student, StudyGroup

    other_dept = Department(name="Другое отделение (sec test)")
    db.add(other_dept)
    db.flush()
    other_group = StudyGroup(code="SECTEST1", course=1, department_id=other_dept.id)
    db.add(other_group)
    db.flush()

    student = Student(
        last_name="Чужой", first_name="Студент", study_group_id=other_group.id,
        enrolled_at=datetime.date(2026, 9, 1),
    )
    db.add(student)
    db.commit()

    r = client.patch(
        f"/admin/students/{student.id}/status", headers=dept_head_headers,
        json={"status": "expelled"},
    )
    assert r.status_code == 403


# --- Дублирующие основные назначения кураторов ---


def test_new_curator_assignment_ends_previous_one(client, admin_headers, imported, db):
    from app.models import CuratorAssignment, Role, StudyGroup, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curators = db.query(User).filter(User.role_id == curator_role.id).limit(2).all()
    group = db.query(StudyGroup).filter(StudyGroup.course == 1).first()

    r = client.post(
        "/admin/curator-assignments", headers=admin_headers,
        json={
            "study_group_id": group.id, "user_id": curators[1].id, "role_type": "curator",
            "start_date": "2026-09-20",
        },
    )
    assert r.status_code == 201, r.text

    active = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.study_group_id == group.id, CuratorAssignment.role_type == "curator")
        .filter((CuratorAssignment.end_date.is_(None)) | (CuratorAssignment.end_date >= datetime.date(2026, 9, 25)))
        .all()
    )
    assert len(active) == 1, "на группе не должно быть двух активных основных кураторов одновременно"
    assert active[0].user_id == curators[1].id
