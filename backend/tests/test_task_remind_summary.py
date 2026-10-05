"""Этап 13: «Напомнить отстающим» и сводка ответов по задаче — права по ролям, охват, частота."""
import datetime

from app.models import AuditLog, Department, InAppNotification, StudyGroup, TaskAssignment
from tests.test_tasks import _create, _field_keys, _my_assignment_id, _students


def _reminders(db, kind="task_manual_reminder"):
    db.expire_all()
    return db.query(InAppNotification).filter(InAppNotification.kind == kind).all()


def test_remind_notifies_only_groups_without_answer(client, admin_headers, curator_headers, curator_user, curator_group, imported, db):
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool", "required": True}])
    total = task["progress"]["total"]
    # Группа куратора отправила ответ — ей не напоминаем.
    aid = _my_assignment_id(client, curator_headers, task["id"])
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"group_values": {task["fields"][0]["key"]: True}})
    client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)

    r = client.post(f"/tasks/{task['id']}/remind", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] + body["skipped"] == total - 1  # без отправившей; группы без куратора — в skipped
    assert body["sent"] > 0
    reminded_ids = {n.entity_id for n in _reminders(db)}
    assert str(aid) not in reminded_ids
    assert all(n.user_id != curator_user.id for n in _reminders(db))
    assert db.query(AuditLog).filter(AuditLog.action == "task.remind").count() == 1


def test_remind_is_throttled_per_group(client, admin_headers, edu_department_headers, imported, db):
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    first = client.post(f"/tasks/{task['id']}/remind", headers=admin_headers).json()
    count = len(_reminders(db))
    # Повтор от другого сотрудника в тот же день — группам уже напомнили.
    second = client.post(f"/tasks/{task['id']}/remind", headers=edu_department_headers).json()
    assert second["sent"] == 0 and second["skipped"] == first["sent"] + first["skipped"]
    assert len(_reminders(db)) == count

    # Через сутки можно снова.
    for n in _reminders(db):
        n.created_at = n.created_at - datetime.timedelta(hours=21)
    db.commit()
    assert client.post(f"/tasks/{task['id']}/remind", headers=admin_headers).json()["sent"] == first["sent"]


def test_remind_respects_department_scope(client, admin_headers, dept_head_headers, dept_head_user, imported, db):
    other = Department(name="Другое отделение")
    db.add(other)
    db.flush()
    stranger = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).order_by(StudyGroup.id.desc()).first()
    stranger.department_id = other.id
    db.commit()
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    client.post(f"/tasks/{task['id']}/remind", headers=dept_head_headers)
    stranger_assignment = db.query(TaskAssignment).filter(
        TaskAssignment.task_id == task["id"], TaskAssignment.study_group_id == stranger.id
    ).one()
    assert str(stranger_assignment.id) not in {n.entity_id for n in _reminders(db)}


def test_remind_closed_task_and_roles(client, admin_headers, curator_headers, imported, db):
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    assert client.post(f"/tasks/{task['id']}/remind", headers=curator_headers).status_code == 403
    assert client.post("/tasks/99999/remind", headers=admin_headers).status_code == 404
    client.patch(f"/tasks/{task['id']}", headers=admin_headers, json={"is_closed": True})
    assert client.post(f"/tasks/{task['id']}/remind", headers=admin_headers).status_code == 400


def test_dept_head_of_other_department_cannot_remind_or_see_summary(client, admin_headers, imported, db):
    from app.core.security import hash_password
    from app.models import Role, RoleCode, User

    other = Department(name="Чужое отделение")
    db.add(other)
    db.flush()
    role = db.query(Role).filter(Role.code == RoleCode.DEPT_HEAD.value).one()
    db.add(User(username="zav2", full_name="Зав. Чужим", role_id=role.id, department_id=other.id, password_hash=hash_password("Zav2Pass123!")))
    db.commit()
    headers = {"Authorization": "Bearer " + client.post("/auth/login", json={"username": "zav2", "password": "Zav2Pass123!"}).json()["access_token"]}
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    assert client.post(f"/tasks/{task['id']}/remind", headers=headers).status_code == 403
    assert client.get(f"/tasks/{task['id']}/summary", headers=headers).status_code == 403


def test_summary_counts_only_sent_answers(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    fields = [
        {"label": "Кружки", "type": "multiselect", "options": ["Спорт", "Танцы"]},
        {"label": "Не посещает", "type": "bool"},
        {"label": "Комментарий", "type": "text"},
    ]
    task = _create(client, admin_headers, fields=fields)
    keys = _field_keys(task)
    a, b, *rest = _students(db, curator_group)
    aid = _my_assignment_id(client, curator_headers, task["id"])
    url = f"/tasks/{task['id']}/summary"

    rows = [
        {"student_id": a.id, "values": {keys["Кружки"]: ["Спорт", "Танцы"], keys["Не посещает"]: False, keys["Комментарий"]: "ок"}},
        {"student_id": b.id, "values": {keys["Кружки"]: ["Спорт"]}},
    ] + [{"student_id": s.id, "values": {keys["Не посещает"]: True}} for s in rest]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": rows})
    # Черновик в сводку не попадает.
    assert client.get(url, headers=admin_headers).json()["answers"] == 0

    client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)
    summary = client.get(url, headers=dept_head_headers).json()
    assert summary["groups"] == 1 and summary["answers"] == len(rows)
    by_key = {f["key"]: f for f in summary["fields"]}
    assert by_key[keys["Кружки"]]["counts"] == [{"label": "Спорт", "count": 2}, {"label": "Танцы", "count": 1}]
    assert by_key[keys["Не посещает"]]["counts"] == [{"label": "да", "count": len(rest)}, {"label": "нет", "count": 1}]
    assert by_key[keys["Комментарий"]]["filled"] == 1 and by_key[keys["Комментарий"]]["counts"] == []
    # Имён студентов в сводке нет.
    assert a.last_name not in str(summary)


def test_summary_requires_manager(client, admin_headers, curator_headers, imported):
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    assert client.get(f"/tasks/{task['id']}/summary", headers=curator_headers).status_code == 403
    summary = client.get(f"/tasks/{task['id']}/summary", headers=admin_headers).json()
    assert summary == {"groups": 0, "answers": 0, "fields": [
        {"key": "f1", "label": "Сдано", "type": "bool", "filled": 0, "counts": [{"label": "да", "count": 0}, {"label": "нет", "count": 0}]}
    ]}


def test_task_detail_marks_locked_steps(client, admin_headers, imported):
    first = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    second = client.post("/tasks", headers=admin_headers, json={
        "title": "Шаг 2", "collect_mode": "group", "reviewer_rule": "none", "fields": [{"label": "Сдано", "type": "bool"}],
        "due_date": str(datetime.date.today() + datetime.timedelta(days=20)), "scope": {"all_groups": True},
        "after_task_id": first["id"], "unlock_on": "accepted",
    }).json()
    assert all(a["is_locked"] for a in second["assignments"])
    assert not any(a["is_locked"] for a in first["assignments"])


def test_task_list_has_author_id_for_my_filter(client, admin_headers, imported, db):
    from app.models import User

    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool"}])
    admin = db.query(User).filter(User.username == "admin").one()
    row = next(r for r in client.get("/tasks", headers=admin_headers).json() if r["id"] == task["id"])
    assert row["author_id"] == admin.id


# ---------- предпросмотр охвата для мастера создания ----------

def test_scope_preview_counts_groups_students_and_curators(client, admin_headers, imported, db):
    from app.models import CuratorAssignment, Student

    r = client.post("/tasks/scope-preview", headers=admin_headers, json={"all_groups": True})
    assert r.status_code == 200
    body = r.json()
    active = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).all()
    assert body["groups"] == len(active)
    assert body["students"] == db.query(Student).filter(Student.study_group_id.in_([g.id for g in active]), Student.left_at.is_(None)).count()
    assert body["curators"] == len({a.user_id for a in db.query(CuratorAssignment).filter(CuratorAssignment.end_date.is_(None))})
    # В синтетическом наборе есть вакансии — группы без куратора перечислены по коду.
    assert body["without_curator"] and all(isinstance(code, str) for code in body["without_curator"])

    one = active[0]
    r = client.post("/tasks/scope-preview", headers=admin_headers, json={"group_ids": [one.id]})
    assert r.json()["groups"] == 1
    r = client.post("/tasks/scope-preview", headers=admin_headers, json={"all_groups": True, "exclude_group_ids": [one.id]})
    assert r.json()["groups"] == len(active) - 1


def test_scope_preview_empty_scope_and_roles(client, admin_headers, curator_headers, imported):
    assert client.post("/tasks/scope-preview", headers=admin_headers, json={}).json() == {
        "groups": 0, "students": 0, "curators": 0, "without_curator": []
    }
    assert client.post("/tasks/scope-preview", headers=curator_headers, json={"all_groups": True}).status_code == 403


def test_scope_preview_is_limited_to_own_department_for_dept_head(client, dept_head_headers, dept_head_user, imported, db):
    other = Department(name="Другое отделение")
    db.add(other)
    db.flush()
    stranger = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).order_by(StudyGroup.id.desc()).first()
    stranger.department_id = other.id
    db.commit()
    own = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True), StudyGroup.department_id == dept_head_user.department_id).count()
    assert client.post("/tasks/scope-preview", headers=dept_head_headers, json={"all_groups": True}).json()["groups"] == own
