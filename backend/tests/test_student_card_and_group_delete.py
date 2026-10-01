"""Карточка студента (GET /students/{id}) и полное удаление группы
вместе с историей (DELETE /admin/groups/{id}?force=true&confirm_code=...)."""
import datetime

from app.core.security import hash_password
from app.models import (
    AbsencePeriod,
    AttendanceMark,
    AuditLog,
    CuratorAssignment,
    DaySubmission,
    Department,
    Role,
    RoleCode,
    Student,
    StudentGroupMembership,
    StudyGroup,
    User,
)
from app.services import attendance_service, calendar_service


def _admin(db):
    return db.query(User).join(Role).filter(Role.code == RoleCode.ADMIN.value).one()


def _recent_study_day(db, group, today):
    day = today
    for _ in range(14):
        if calendar_service.is_study_day(db, day, study_group_id=group.id, course=group.course):
            return day
        day -= datetime.timedelta(days=1)
    raise AssertionError("нет учебного дня за две недели")


def _submit_with_absence(db, group, today, code="н"):
    day = _recent_study_day(db, group, today)
    students = attendance_service.get_active_students(db, group.id, day)
    attendance_service.submit_day(
        db, group.id, day,
        [{"student_id": students[0].id, "mark_code": code, "comment": "болел", "basis_reference": None}],
        _admin(db),
    )
    return day, students[0]


def test_student_card_has_group_curator_stats_and_marks(client, admin_headers, db, curator_group, today):
    day, student = _submit_with_absence(db, curator_group, today)

    r = client.get(f"/students/{student.id}", headers=admin_headers)
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["full_name"] == student.full_name
    assert card["status"] == "studying"
    assert card["enrolled_at"] == str(student.enrolled_at)
    assert card["group"]["code"] == curator_group.code
    assert card["group"]["department_name"] == "Диджитал"
    assert card["curator_name"]
    assert [h["group_code"] for h in card["group_history"]] == [curator_group.code]
    assert card["stats"]["in_list"] == 1
    assert card["stats"]["absent_total"] == 1
    assert card["stats"]["by_code"] == {"н": 1}
    assert card["recent_marks"][0]["date"] == str(day)
    assert card["recent_marks"][0]["code"] == "н"
    assert card["recent_marks"][0]["comment"] == "болел"


def test_student_card_unknown_student_404(client, admin_headers, imported):
    assert client.get("/students/999999", headers=admin_headers).status_code == 404


def test_student_card_curator_sees_own_group_only(client, curator_headers, db, curator_group):
    own = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    assert client.get(f"/students/{own.id}", headers=curator_headers).status_code == 200

    foreign = db.query(Student).filter(Student.study_group_id != curator_group.id).first()
    assert client.get(f"/students/{foreign.id}", headers=curator_headers).status_code == 403
    assert client.get(f"/students/{foreign.id}/attendance?year=2026&month=9", headers=curator_headers).status_code == 403


def test_student_card_dept_head_only_own_department(client, dept_head_headers, db, imported):
    own = db.query(Student).first()
    assert client.get(f"/students/{own.id}", headers=dept_head_headers).status_code == 200

    other = Department(name="Чужое отделение")
    db.add(other)
    db.flush()
    foreign_group = StudyGroup(code="ЧУЖ-1", course=1, department_id=other.id)
    db.add(foreign_group)
    db.flush()
    foreign_student = Student(
        last_name="Чужой", first_name="Студент", study_group_id=foreign_group.id,
        enrolled_at=datetime.date(2026, 9, 1),
    )
    db.add(foreign_student)
    db.commit()
    assert client.get(f"/students/{foreign_student.id}", headers=dept_head_headers).status_code == 403


def test_deletion_preview_counts(client, admin_headers, db, curator_group, today):
    _submit_with_absence(db, curator_group, today)
    students = db.query(Student).filter(Student.study_group_id == curator_group.id).count()

    r = client.get(f"/admin/groups/{curator_group.id}/deletion-preview", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == curator_group.code
    assert body["students"] == students
    assert body["attendance_marks"] == 1
    assert body["day_submissions"] == 1
    assert body["curator_assignments"] >= 1


def test_force_delete_requires_matching_code(client, admin_headers, db, curator_group):
    r = client.delete(f"/admin/groups/{curator_group.id}?force=true", headers=admin_headers)
    assert r.status_code == 400
    r = client.delete(f"/admin/groups/{curator_group.id}?force=true&confirm_code=НЕ-ТО", headers=admin_headers)
    assert r.status_code == 400
    assert db.get(StudyGroup, curator_group.id) is not None


def test_force_delete_removes_group_with_all_history_but_nothing_else(
    client, admin_headers, db, curator_group, today
):
    group_id, code = curator_group.id, curator_group.code
    _submit_with_absence(db, curator_group, today)
    other_group = db.query(StudyGroup).filter(StudyGroup.id != group_id).first()
    other_students_before = db.query(Student).filter(Student.study_group_id == other_group.id).count()
    group_student_ids = [s.id for s in db.query(Student).filter(Student.study_group_id == group_id)]
    total_students_before = db.query(Student).count()

    r = client.delete(f"/admin/groups/{group_id}?force=true&confirm_code={code}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    assert code in r.json()["detail"]

    db.expire_all()
    assert db.get(StudyGroup, group_id) is None
    assert db.query(Student).filter(Student.id.in_(group_student_ids)).count() == 0
    assert db.query(Student).count() == total_students_before - len(group_student_ids)
    assert db.query(AttendanceMark).count() == 0
    assert db.query(AbsencePeriod).count() == 0
    assert db.query(DaySubmission).filter(DaySubmission.study_group_id == group_id).count() == 0
    assert db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id == group_id).count() == 0
    assert db.query(StudentGroupMembership).filter(StudentGroupMembership.study_group_id == group_id).count() == 0
    assert db.query(Student).filter(Student.study_group_id == other_group.id).count() == other_students_before

    entry = db.query(AuditLog).filter(AuditLog.action == "group.delete_cascade").one()
    assert entry.old_value == code
    assert "students=" in entry.new_value


def test_force_delete_keeps_students_transferred_out_of_the_group(client, admin_headers, db, curator_group):
    group_id, code = curator_group.id, curator_group.code
    other_group = db.query(StudyGroup).filter(StudyGroup.id != group_id).first()
    moved = db.query(Student).filter(Student.study_group_id == group_id).first()

    r = client.patch(f"/admin/students/{moved.id}", headers=admin_headers, json={"study_group_id": other_group.id})
    assert r.status_code == 200, r.text

    r = client.delete(f"/admin/groups/{group_id}?force=true&confirm_code={code}", headers=admin_headers)
    assert r.status_code == 200, r.text

    db.expire_all()
    survivor = db.get(Student, moved.id)
    assert survivor is not None and survivor.study_group_id == other_group.id
    memberships = db.query(StudentGroupMembership).filter(StudentGroupMembership.student_id == moved.id).all()
    assert [m.study_group_id for m in memberships] == [other_group.id]


def test_force_delete_forbidden_for_dept_head(client, dept_head_headers, db, curator_group):
    r = client.delete(
        f"/admin/groups/{curator_group.id}?force=true&confirm_code={curator_group.code}",
        headers=dept_head_headers,
    )
    assert r.status_code == 403
    assert db.get(StudyGroup, curator_group.id) is not None


def test_plain_delete_of_active_group_still_requires_archive(client, admin_headers, db, curator_group):
    r = client.delete(f"/admin/groups/{curator_group.id}", headers=admin_headers)
    assert r.status_code == 400
