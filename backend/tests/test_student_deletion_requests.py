"""Полное удаление студента: зав. отделением — сам, куратор — через запрос с одобрением."""
import pytest


@pytest.fixture()
def archived_student(client, admin_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students

    student = get_active_students(db, curator_group.id, today)[0]
    sid = student.id
    client.patch(f"/admin/students/{sid}", headers=admin_headers, json={"status": "expelled"})
    return sid


def test_curator_cannot_delete_directly(client, curator_headers, archived_student):
    assert client.delete(f"/admin/students/{archived_student}?force=true", headers=curator_headers).status_code == 403


def test_curator_request_approved_by_admin_erases_student(client, curator_headers, admin_headers, archived_student, db):
    from app.models import Student, StudentDeletionRequest

    r = client.post("/student-deletions", headers=curator_headers, json={"student_id": archived_student, "reason": "Ошибка в списке"})
    assert r.status_code == 201, r.text
    req_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    # повторный запрос, пока первый не решён, не принимается
    assert client.post("/student-deletions", headers=curator_headers, json={"student_id": archived_student, "reason": "Ещё раз"}).status_code == 400
    # куратор не решает сам
    assert client.post(f"/student-deletions/{req_id}/approve", headers=curator_headers).status_code == 403

    assert [x["id"] for x in client.get("/student-deletions", headers=admin_headers).json()] == [req_id]
    r = client.post(f"/student-deletions/{req_id}/approve", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    db.expire_all()
    assert db.get(Student, archived_student) is None
    assert db.query(StudentDeletionRequest).count() == 0


def test_request_rejected_and_cancelled(client, curator_headers, admin_headers, archived_student):
    req_id = client.post("/student-deletions", headers=curator_headers, json={"student_id": archived_student, "reason": "Лишний"}).json()["id"]
    r = client.post(f"/student-deletions/{req_id}/reject", headers=admin_headers, json={"comment": "Нужен для отчёта"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.post(f"/student-deletions/{req_id}/approve", headers=admin_headers).status_code == 409

    req2 = client.post("/student-deletions", headers=curator_headers, json={"student_id": archived_student, "reason": "Снова"}).json()["id"]
    assert client.post(f"/student-deletions/{req2}/cancel", headers=admin_headers).status_code == 403
    assert client.post(f"/student-deletions/{req2}/cancel", headers=curator_headers).json()["status"] == "cancelled"


def test_studying_student_cannot_be_requested(client, curator_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students

    sid = get_active_students(db, curator_group.id, today)[0].id
    assert client.post("/student-deletions", headers=curator_headers, json={"student_id": sid, "reason": "Просто так"}).status_code == 400


def test_dept_head_deletes_own_department_student_completely(client, dept_head_headers, archived_student, db):
    from app.models import Student

    r = client.delete(f"/admin/students/{archived_student}?force=true", headers=dept_head_headers)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Student, archived_student) is None


def test_dept_head_manages_everyone_in_own_department(client, dept_head_headers, dept_head_user, db):
    from app.models import Role, User

    tutor_role = db.query(Role).filter(Role.code == "tutor").one()
    r = client.post("/admin/users", headers=dept_head_headers, json={
        "username": "tutor_x", "full_name": "Тьютор Тест", "role": "tutor",
        "password": "Xk9#mPq2vLz!", "department_id": dept_head_user.department_id,
    })
    assert r.status_code == 201, r.text
    assert db.query(User).filter(User.username == "tutor_x").one().role_id == tutor_role.id
    r = client.post("/admin/users", headers=dept_head_headers, json={
        "username": "adm_x", "full_name": "Админ Тест", "role": "admin", "password": "Xk9#mPq2vLz!",
    })
    assert r.status_code == 403
