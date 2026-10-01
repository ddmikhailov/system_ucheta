import datetime


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

    # commit(), а не только expire_all() — см. пояснение в
    # test_end_curator_assignment_keeps_history (MySQL REPEATABLE READ).
    db.commit()
    after = stats_service.compute_period_stats(db, today, today, study_group_id=curator_group.id)
    assert after.absent_total == 0
    assert after.percent == 100.0

    from app.models import AuditLog

    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "mark_code.flag_change", AuditLog.entity_id == str(mark_code.id))
        .one()
    )
    assert "counts_as_present" in entry.old_value
    assert "counts_as_present" in entry.new_value


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


def test_group_list_shows_and_can_remove_deputy(client, admin_headers, imported, db):
    """Раньше заместителя не было видно в /admin/groups и снять его было
    нечем на фронте (см. TODO.md 3)."""
    from app.models import Role, StudyGroup, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curators = db.query(User).filter(User.role_id == curator_role.id).limit(2).all()
    group = db.query(StudyGroup).filter(StudyGroup.course == 1).first()

    r = client.post(
        "/admin/curator-assignments", headers=admin_headers,
        json={
            "study_group_id": group.id, "user_id": curators[1].id, "role_type": "deputy",
            "start_date": "2026-09-01",
        },
    )
    assert r.status_code == 201, r.text

    r = client.get("/admin/groups", headers=admin_headers)
    row = next(g for g in r.json() if g["id"] == group.id)
    assert row["deputy_name"] == curators[1].full_name
    assert row["deputy_assignment_id"] is not None
    deputy_assignment_id = row["deputy_assignment_id"]

    r = client.post(f"/admin/curator-assignments/{deputy_assignment_id}/end", headers=admin_headers)
    assert r.status_code == 200

    # end_date выставляется на сегодня включительно (см. is_active_on) — тот,
    # кого сняли сегодня, ещё числился ответственным сегодня же, поэтому
    # проверяем сам факт простановки даты окончания, а не мгновенное
    # исчезновение из /admin/groups в тот же день.
    from app.models import CuratorAssignment

    from app.core.time import today_local

    assignment = db.get(CuratorAssignment, deputy_assignment_id)
    assert assignment.end_date is not None
    assert assignment.end_date <= today_local()


def test_audit_log_records_ip_address(client, admin_headers, imported, db):
    """Раньше audit_log.ip_address нигде не заполнялся (см. TODO.md 5)."""
    from app.models import AuditLog, MarkCode

    mark_code = db.query(MarkCode).first()
    r = client.patch(
        f"/admin/mark-codes/{mark_code.id}", headers=admin_headers,
        json={"counts_as_present": not mark_code.counts_as_present},
    )
    assert r.status_code == 200

    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "mark_code.flag_change", AuditLog.entity_id == str(mark_code.id))
        .one()
    )
    assert entry.ip_address is not None


def test_previously_unlogged_admin_actions_now_write_audit_log(client, admin_headers, imported, db):
    """Раньше create_department/update_department/create_group/create_student/
    create_user не писали в audit_log вообще
    (см. TODO.md 5)."""
    from app.models import AuditLog, Department, StudyGroup, User

    r = client.post("/admin/departments", headers=admin_headers, json={"name": "Аудит-тест отделение"})
    assert r.status_code == 201
    dept_id = r.json()["id"]
    assert db.query(AuditLog).filter(AuditLog.action == "department.create", AuditLog.entity_id == str(dept_id)).first()

    r = client.patch(f"/admin/departments/{dept_id}", headers=admin_headers, json={"name": "Аудит-тест 2"})
    assert r.status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == "department.rename", AuditLog.entity_id == str(dept_id)).first()

    r = client.post(
        "/admin/groups", headers=admin_headers,
        json={"code": "AUDIT-GRP", "course": 1, "department_id": dept_id, "study_form": None},
    )
    assert r.status_code == 201
    group_id = r.json()["id"]
    assert db.query(AuditLog).filter(AuditLog.action == "group.create", AuditLog.entity_id == str(group_id)).first()

    r = client.post(
        "/admin/students", headers=admin_headers,
        json={
            "last_name": "Аудит", "first_name": "Тест", "middle_name": None,
            "study_group_id": group_id, "enrolled_at": "2026-09-01",
        },
    )
    assert r.status_code == 201
    student_id = r.json()["id"]
    assert db.query(AuditLog).filter(AuditLog.action == "student.create", AuditLog.entity_id == str(student_id)).first()

    r = client.post(
        "/admin/users", headers=admin_headers,
        json={"username": "audituser", "full_name": "Аудит Юзер", "role": "curator", "department_id": dept_id},
    )
    assert r.status_code == 201
    user_id = r.json()["id"]
    assert db.query(AuditLog).filter(AuditLog.action == "user.create", AuditLog.entity_id == str(user_id)).first()
