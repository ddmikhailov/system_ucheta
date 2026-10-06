"""Профиль пользователя для администрации (интерфейс 3.0): закрепления, дисциплина сдачи
дней, задачи, индивидуальная работа и журнал действий."""
import datetime

from app.core.time import today_local, utcnow
from app.models import AuditLog, CuratorAssignment, DaySubmission, Department, StudentNote, Student, User
from app.services import calendar_service, user_profile_service


def _expected_days(db, curator_user, group):
    today = today_local()
    start = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.user_id == curator_user.id, CuratorAssignment.study_group_id == group.id)
        .one()
        .start_date
    )
    days = calendar_service.study_days_by_group(
        db, today - datetime.timedelta(days=30), today - datetime.timedelta(days=1), [group]
    )[group.id]
    return [d for d in days if d >= start]


def test_admin_sees_curator_profile_with_groups_and_discipline(client, admin_headers, db, curator_user, curator_group):
    days = _expected_days(db, curator_user, curator_group)
    if days:
        db.add(DaySubmission(study_group_id=curator_group.id, date=days[0], submitted_by_user_id=curator_user.id, is_on_time=True))
    if len(days) > 1:
        db.add(DaySubmission(study_group_id=curator_group.id, date=days[1], submitted_by_user_id=curator_user.id, is_on_time=False))
    db.commit()

    r = client.get(f"/admin/users/{curator_user.id}/profile", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == curator_user.username
    current = [g for g in body["groups"] if g["is_current"]]
    assert [g["group_id"] for g in current] == [curator_group.id]
    assert current[0]["role_type"] == "curator"
    studying = db.query(Student).filter(Student.study_group_id == curator_group.id, Student.status == "studying").count()
    assert current[0]["students_count"] == studying

    disc = body["discipline"]
    assert disc["study_days"] == len(days)
    assert disc["on_time"] == min(len(days), 1)
    assert disc["late"] == (1 if len(days) > 1 else 0)
    assert disc["missed"] == len(days) - disc["submitted"]
    assert len(body["activity_30d"]) == 30
    assert body["activity_30d"][-1]["date"] == str(today_local())


def test_profile_counts_individual_work_and_activity(client, admin_headers, db, curator_user, curator_group):
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    db.add(StudentNote(student_id=student.id, author_id=curator_user.id, kind="talk", text="Синтетическая беседа",
                       follow_up_on=today_local(), follow_up_done=False))
    db.add(AuditLog(user_id=curator_user.id, action="dossier.note_add", entity_type="student", entity_id=str(student.id),
                    new_value="секрет", created_at=utcnow()))
    db.commit()
    body = client.get(f"/admin/users/{curator_user.id}/profile", headers=admin_headers).json()
    assert body["notes_written_30d"] == 1
    assert body["follow_ups_open"] == 1
    assert body["last_activity_at"] is not None
    assert body["activity_30d"][-1]["count"] >= 1


def test_activity_feed_pages_and_hides_values(client, admin_headers, db, curator_user):
    for i in range(3):
        db.add(AuditLog(user_id=curator_user.id, action="mark.create", entity_type="attendance_mark",
                        entity_id=str(i), old_value="Иванов", new_value="Петров"))
    db.add(AuditLog(user_id=curator_user.id, action="task.submit", entity_type="task_assignment", entity_id="9"))
    db.commit()

    first = client.get(f"/admin/users/{curator_user.id}/activity?limit=2", headers=admin_headers).json()
    assert [i["action"] for i in first["items"]] == ["task.submit", "mark.create"]
    assert "old_value" not in first["items"][0] and "new_value" not in first["items"][0]
    assert first["next_before_id"] is not None
    rest = client.get(
        f"/admin/users/{curator_user.id}/activity?limit=2&before_id={first['next_before_id']}", headers=admin_headers
    ).json()
    assert [i["action"] for i in rest["items"]] == ["mark.create", "mark.create"]
    assert rest["next_before_id"] is None

    marks = client.get(f"/admin/users/{curator_user.id}/activity?area=mark", headers=admin_headers).json()
    assert {i["action"] for i in marks["items"]} == {"mark.create"}
    bad = client.get(f"/admin/users/{curator_user.id}/activity?area=mark%25", headers=admin_headers)
    assert bad.status_code == 422


def test_profile_access(client, db, curator_user, curator_headers, edu_department_headers, admin_headers):
    assert client.get(f"/admin/users/{curator_user.id}/profile", headers=curator_headers).status_code == 403
    assert client.get(f"/admin/users/{curator_user.id}/activity", headers=curator_headers).status_code == 403
    assert client.get(f"/admin/users/{curator_user.id}/profile", headers=edu_department_headers).status_code == 200
    assert client.get("/admin/users/999999/profile", headers=admin_headers).status_code == 404


def test_dept_head_sees_only_own_department(client, db, dept_head_user, dept_head_headers, curator_user):
    admin = db.query(User).filter(User.username == "admin").one()
    assert client.get(f"/admin/users/{admin.id}/profile", headers=dept_head_headers).status_code == 403
    other = Department(name="Другое отделение (синт.)")
    db.add(other)
    db.flush()
    curator_user.department_id = other.id
    db.commit()
    assert client.get(f"/admin/users/{curator_user.id}/activity", headers=dept_head_headers).status_code == 403
    curator_user.department_id = dept_head_user.department_id
    db.commit()
    assert client.get(f"/admin/users/{curator_user.id}/profile", headers=dept_head_headers).status_code == 200


def test_profile_without_groups(db, seeded):
    admin = db.query(User).filter(User.username == "admin").one()
    profile = user_profile_service.build_profile(db, admin)
    assert profile["groups"] == []
    assert profile["discipline"].study_days == 0 and profile["discipline"].percent_on_time is None
    assert profile["tasks"].total == 0
