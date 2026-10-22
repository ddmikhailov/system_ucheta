"""Столбец «Студентов» в таблице групп админки: считаются только учащиеся (не отпускники и не отчисленные)."""
from app.models import Student, StudentStatus


def test_groups_list_has_students_count(client, db, imported, admin_headers):
    rows = client.get("/admin/groups", headers=admin_headers).json()
    assert rows
    for row in rows:
        expected = db.query(Student).filter(
            Student.study_group_id == row["id"], Student.status == StudentStatus.STUDYING
        ).count()
        assert row["students_count"] == expected
    assert sum(r["students_count"] for r in rows) > 0


def test_students_count_ignores_expelled(client, db, imported, admin_headers):
    group_id = next(r["id"] for r in client.get("/admin/groups", headers=admin_headers).json() if r["students_count"] > 0)
    before = next(r for r in client.get("/admin/groups", headers=admin_headers).json() if r["id"] == group_id)["students_count"]
    student = db.query(Student).filter(Student.study_group_id == group_id, Student.status == StudentStatus.STUDYING).first()
    student.status = StudentStatus.EXPELLED
    db.commit()
    after = next(r for r in client.get("/admin/groups", headers=admin_headers).json() if r["id"] == group_id)["students_count"]
    assert after == before - 1
