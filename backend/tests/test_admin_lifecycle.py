"""М4: полное редактирование, архив и безопасное удаление групп, студентов
и пользователей — правки не должны терять историю посещаемости.
"""
import datetime


def test_update_group_fields(client, admin_headers, imported, db):
    from app.models import Department, StudyGroup

    dept = db.query(Department).one()
    group = db.query(StudyGroup).first()

    r = client.patch(
        f"/admin/groups/{group.id}", headers=admin_headers,
        json={"course": 2, "study_form": "заочная"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["course"] == 2
    assert r.json()["department_id"] == dept.id  # не тронут


def test_archive_and_restore_empty_group(client, admin_headers, db):
    from app.models import Department, StudyGroup

    dept = db.query(Department).one()
    r = client.post(
        "/admin/groups", headers=admin_headers,
        json={"code": "ПУСТАЯ101", "course": 1, "department_id": dept.id, "study_form": None},
    )
    group_id = r.json()["id"]

    r = client.patch(f"/admin/groups/{group_id}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # Пустую (без студентов и истории) группу можно удалить насовсем из архива.
    r = client.delete(f"/admin/groups/{group_id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = client.get("/admin/groups", headers=admin_headers)
    assert not any(g["id"] == group_id for g in r.json())


def test_cannot_delete_active_group(client, admin_headers, imported, db):
    from app.models import StudyGroup

    group = db.query(StudyGroup).first()
    r = client.delete(f"/admin/groups/{group.id}", headers=admin_headers)
    assert r.status_code == 400


def test_cannot_hard_delete_group_with_history(client, admin_headers, imported, db):
    from app.models import StudyGroup

    group = db.query(StudyGroup).filter(StudyGroup.students.any()).first()
    client.patch(f"/admin/groups/{group.id}", headers=admin_headers, json={"is_active": False})

    r = client.delete(f"/admin/groups/{group.id}", headers=admin_headers)
    assert r.status_code == 409

    # Группа осталась в базе (архивной).
    r = client.get(f"/admin/groups?department_id={group.department_id}", headers=admin_headers)
    assert any(g["id"] == group.id for g in r.json())


def test_dept_head_cannot_move_group_to_another_department(client, dept_head_headers, imported, db):
    from app.models import Department, StudyGroup

    other = Department(name="Соседнее отделение")
    db.add(other)
    db.commit()
    group = db.query(StudyGroup).first()
    original_dept = group.department_id

    r = client.patch(
        f"/admin/groups/{group.id}", headers=dept_head_headers,
        json={"department_id": other.id, "study_form": "очная"},
    )
    assert r.status_code == 200
    assert r.json()["department_id"] == original_dept  # тихо проигнорировано
    assert r.json()["study_form"] == "очная"  # остальное применилось


def test_update_and_transfer_student(client, admin_headers, imported, db):
    from app.models import Student, StudyGroup

    student = db.query(Student).first()
    other_group = db.query(StudyGroup).filter(StudyGroup.id != student.study_group_id).first()

    r = client.patch(
        f"/admin/students/{student.id}", headers=admin_headers,
        json={"first_name": "Тест", "study_group_id": other_group.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["study_group_id"] == other_group.id
    assert "Тест" in r.json()["full_name"]


def test_expel_then_delete_student_without_history(client, admin_headers, imported, db):
    from app.models import Student

    student = db.query(Student).first()
    r = client.patch(
        f"/admin/students/{student.id}", headers=admin_headers,
        json={"status": "expelled", "left_at": "2026-09-22"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "expelled"

    r = client.delete(f"/admin/students/{student.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_cannot_delete_studying_student(client, admin_headers, imported, db):
    from app.models import Student

    student = db.query(Student).first()
    r = client.delete(f"/admin/students/{student.id}", headers=admin_headers)
    assert r.status_code == 400


def test_delete_student_with_marks_anonymizes(client, admin_headers, curator_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students

    student = get_active_students(db, curator_group.id, today)[0]
    client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date={today}",
        headers=curator_headers,
        json={"exceptions": [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}]},
    )

    client.patch(f"/admin/students/{student.id}", headers=admin_headers, json={"status": "expelled"})
    r = client.delete(f"/admin/students/{student.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["anonymized"] is True
    assert r.json()["deleted"] is False

    r = client.get(f"/admin/students?study_group_id={curator_group.id}", headers=admin_headers)
    row = next(s for s in r.json() if s["id"] == student.id)
    assert "Удалённый" in row["full_name"]


def test_archive_curator_and_delete(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()

    r = client.patch(f"/admin/users/{curator.id}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r = client.delete(f"/admin/users/{curator.id}", headers=admin_headers)
    assert r.status_code == 200
    # У импортированного куратора есть назначение на группу — история есть.
    assert r.json()["anonymized"] is True


def test_cannot_archive_or_delete_self(client, admin_headers, db):
    from app.models import User

    admin = db.query(User).filter(User.username == "admin").one()
    r = client.patch(f"/admin/users/{admin.id}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 400

    r = client.delete(f"/admin/users/{admin.id}", headers=admin_headers)
    assert r.status_code == 400


def test_cannot_delete_active_curator(client, admin_headers, imported, db):
    from app.models import Role, User

    curator_role = db.query(Role).filter(Role.code == "curator").one()
    curator = db.query(User).filter(User.role_id == curator_role.id).first()
    r = client.delete(f"/admin/users/{curator.id}", headers=admin_headers)
    assert r.status_code == 400


def test_end_curator_assignment_keeps_history(client, admin_headers, curator_group, curator_user, db, today):
    from app.models import CuratorAssignment

    assignment = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.study_group_id == curator_group.id, CuratorAssignment.user_id == curator_user.id)
        .one()
    )
    r = client.post(f"/admin/curator-assignments/{assignment.id}/end", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["end_date"] == str(today)

    # Назначение осталось в базе (не удалено) — история сохранена, а не стёрта.
    db.expire_all()
    still_there = db.get(CuratorAssignment, assignment.id)
    assert still_there is not None
    assert still_there.end_date == today

    # end_date — включительно (куратор ведёт группу по этот день включительно),
    # поэтому назавтра он уже не значится куратором.
    assert still_there.is_active_on(today) is True
    assert still_there.is_active_on(today + datetime.timedelta(days=1)) is False


def test_dept_head_cannot_end_assignment_outside_department(client, dept_head_headers, imported, db):
    from app.models import CuratorAssignment, Department

    other_dept = Department(name="Чужое отделение")
    db.add(other_dept)
    db.commit()

    assignment = db.query(CuratorAssignment).first()
    assignment.study_group.department_id = other_dept.id
    db.commit()

    r = client.post(f"/admin/curator-assignments/{assignment.id}/end", headers=dept_head_headers)
    assert r.status_code == 403
