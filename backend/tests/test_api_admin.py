def test_create_department(client, admin_headers):
    r = client.post("/admin/departments", headers=admin_headers, json={"name": "Экономика"})
    assert r.status_code == 201
    assert r.json()["name"] == "Экономика"

    r = client.get("/admin/departments", headers=admin_headers)
    names = [d["name"] for d in r.json()]
    assert "Экономика" in names


def test_create_group_and_assign_curator(client, admin_headers, imported, db):
    from app.models import Department

    dept = db.query(Department).one()
    r = client.post(
        "/admin/groups", headers=admin_headers,
        json={"code": "ТЕСТ101", "course": 1, "department_id": dept.id, "study_form": None},
    )
    assert r.status_code == 201
    group_id = r.json()["id"]
    assert r.json()["curator_name"] is None

    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.post(
        "/admin/curator-assignments", headers=admin_headers,
        json={
            "study_group_id": group_id, "user_id": curator.id,
            "role_type": "curator", "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 201

    r = client.get("/admin/groups", headers=admin_headers)
    group = next(g for g in r.json() if g["id"] == group_id)
    assert group["curator_name"] == curator.full_name


def test_create_and_update_student_status(client, admin_headers, imported, db):
    from app.models import StudyGroup

    group = db.query(StudyGroup).first()
    r = client.post(
        "/admin/students", headers=admin_headers,
        json={
            "last_name": "Тестов", "first_name": "Тест", "middle_name": None,
            "study_group_id": group.id, "enrolled_at": "2026-09-01",
        },
    )
    assert r.status_code == 201
    student_id = r.json()["id"]
    assert r.json()["status"] == "studying"

    r = client.patch(
        f"/admin/students/{student_id}/status", headers=admin_headers,
        json={"status": "academic_leave", "left_at": "2026-10-01"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "academic_leave"
    assert r.json()["left_at"] == "2026-10-01"


def test_mark_codes_flags_affect_stats(client, admin_headers, edu_department_headers, imported, curator_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students
    from app.services import stats_service

    student = get_active_students(db, curator_group.id, today)[0]

    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date={today}",
        headers=curator_headers,
        json={"exceptions": [{"student_id": student.id, "mark_code": "р", "comment": None, "basis_reference": None}]},
    )
    assert r.status_code == 200

    before = stats_service.compute_period_stats(db, today, today, study_group_id=curator_group.id)
    assert before.absent_total == 1

    from app.models import MarkCode

    mark_code = db.query(MarkCode).filter(MarkCode.code == "р").one()
    r = client.patch(
        f"/admin/mark-codes/{mark_code.id}", headers=edu_department_headers,
        json={"counts_as_present": True},
    )
    assert r.status_code == 200

    db.expire_all()
    after = stats_service.compute_period_stats(db, today, today, study_group_id=curator_group.id)
    assert after.absent_total == 0
    assert after.percent == 100.0


def test_users_show_pending_password_state(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    pending_user = db.query(User).filter(User.role_id == curator_role.id, User.password_hash.is_(None)).first()

    r = client.get("/admin/users", headers=admin_headers)
    row = next(u for u in r.json() if u["id"] == pending_user.id)
    assert row["has_password"] is False


def test_calendar_upsert_and_list(client, edu_department_headers):
    r = client.put(
        "/admin/calendar", headers=edu_department_headers,
        json={"date": "2026-11-04", "day_type": "holiday"},
    )
    assert r.status_code == 200
    assert r.json()["day_type"] == "holiday"

    r = client.get(
        "/admin/calendar?date_from=2026-11-01&date_to=2026-11-30", headers=edu_department_headers
    )
    assert r.status_code == 200
    dates = [row["date"] for row in r.json()]
    assert "2026-11-04" in dates


def test_calendar_edit_forbidden_for_dept_head(client, dept_head_headers):
    r = client.put(
        "/admin/calendar", headers=dept_head_headers,
        json={"date": "2026-11-04", "day_type": "holiday"},
    )
    assert r.status_code == 403


def test_leadership_digest_flag_toggle(client, admin_headers, imported, db):
    from app.models import User

    admin = db.query(User).filter(User.username == "admin").one()
    r = client.get("/admin/users", headers=admin_headers)
    row = next(u for u in r.json() if u["id"] == admin.id)
    assert row["receives_leadership_digest"] is False

    r = client.patch(
        f"/admin/users/{admin.id}/leadership-digest", headers=admin_headers,
        json={"receives_leadership_digest": True},
    )
    assert r.status_code == 200
    assert r.json()["receives_leadership_digest"] is True

    r = client.get("/admin/users", headers=admin_headers)
    row = next(u for u in r.json() if u["id"] == admin.id)
    assert row["receives_leadership_digest"] is True


def test_leadership_digest_flag_forbidden_for_edu_department(client, edu_department_headers, imported, db):
    from app.models import User

    admin = db.query(User).filter(User.username == "admin").one()
    r = client.patch(
        f"/admin/users/{admin.id}/leadership-digest", headers=edu_department_headers,
        json={"receives_leadership_digest": True},
    )
    assert r.status_code == 403
