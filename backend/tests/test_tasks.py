"""Задачи от администрации: охват, заполнение куратором, проверка, права, выгрузка."""
import datetime
import io

from openpyxl import load_workbook

from app.models import Department, Student, StudyGroup, Task, TaskAssignment

FIELDS_STUDENT = [
    {"label": "Кружки", "type": "multiselect", "options": ["Спорт", "Танцы", "Робототехника"], "required": False},
    {"label": "Не посещает", "type": "bool", "required": False},
    {"label": "Телефон родителя", "type": "text", "required": True},
]


def _future(days=7):
    return str(datetime.date.today() + datetime.timedelta(days=days))


def _payload(**overrides):
    base = {
        "title": "Кружки доп. образования", "description": "Собрать данные", "collect_mode": "student",
        "reviewer_rule": "dept_head", "due_date": _future(), "fields": FIELDS_STUDENT,
        "scope": {"all_groups": True},
    }
    base.update(overrides)
    return base


def _create(client, headers, **overrides):
    r = client.post("/tasks", headers=headers, json=_payload(**overrides))
    assert r.status_code == 201, r.text
    return r.json()


def _my_assignment_id(client, headers, task_id):
    rows = client.get("/tasks/my", headers=headers).json()
    return next(r["id"] for r in rows if r["task_id"] == task_id)


def _students(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).all()


def _field_keys(task):
    return {f["label"]: f["key"] for f in task["fields"]}


# ---------- создание и охват ----------

def test_admin_creates_task_for_all_groups_and_curator_is_notified(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers)
    active_groups = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).count()
    assert task["progress"]["total"] == active_groups and task["progress"]["new"] == active_groups
    assert [f["key"] for f in task["fields"]] == ["f1", "f2", "f3"]

    mine = client.get("/tasks/my", headers=curator_headers).json()
    assert [(r["title"], r["status"], r["group_code"]) for r in mine] == [
        ("Кружки доп. образования", "new", curator_group.code)
    ]
    notifications = client.get("/notifications", headers=curator_headers).json()
    assert any(n["kind"] == "task_assigned" for n in notifications)


def test_scope_by_department_course_groups_and_exclusions(client, admin_headers, imported, db):
    groups = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).order_by(StudyGroup.id).all()
    first, second = groups[0], groups[1]
    only_two = _create(client, admin_headers, scope={"group_ids": [first.id, second.id]})
    assert only_two["progress"]["total"] == 2
    excluded = _create(client, admin_headers, scope={"all_groups": True, "exclude_group_ids": [first.id]})
    assert excluded["progress"]["total"] == len(groups) - 1
    course = _create(client, admin_headers, scope={"courses": [first.course]})
    assert course["progress"]["total"] == sum(1 for g in groups if g.course == first.course)

    other = Department(name="Другое отделение")
    db.add(other)
    db.commit()
    r = client.post("/tasks", headers=admin_headers, json=_payload(scope={"department_ids": [other.id]}))
    assert r.status_code == 400 and "ни одна группа" in r.json()["detail"]
    assert client.post("/tasks", headers=admin_headers, json=_payload(scope={})).status_code == 400


def test_task_validation(client, admin_headers, imported):
    bad_select = [{"label": "Выбор", "type": "select", "options": []}]
    assert client.post("/tasks", headers=admin_headers, json=_payload(fields=bad_select)).status_code == 400
    assert client.post("/tasks", headers=admin_headers, json=_payload(fields=[])).status_code == 400
    past = str(datetime.date.today() - datetime.timedelta(days=1))
    assert client.post("/tasks", headers=admin_headers, json=_payload(due_date=past)).status_code == 400
    assert client.post("/tasks", headers=admin_headers, json=_payload(collect_mode="everyone")).status_code == 422


def test_dept_head_can_create_only_for_own_department(client, dept_head_headers, dept_head_user, imported, db):
    other = Department(name="Другое отделение")
    db.add(other)
    db.flush()
    foreign = StudyGroup(code="OTH-9", course=1, department_id=other.id)
    db.add(foreign)
    db.commit()
    own_count = db.query(StudyGroup).filter(
        StudyGroup.is_active.is_(True), StudyGroup.department_id == dept_head_user.department_id
    ).count()
    task = _create(client, dept_head_headers)  # «весь колледж» урезается до своего отделения
    assert task["progress"]["total"] == own_count
    assert all(a["group_code"] != "OTH-9" for a in task["assignments"])
    r = client.post("/tasks", headers=dept_head_headers, json=_payload(scope={"group_ids": [foreign.id]}))
    assert r.status_code == 400


def test_curator_and_staff_cannot_create_tasks(client, curator_headers):
    assert client.post("/tasks", headers=curator_headers, json=_payload()).status_code == 403
    assert client.get("/tasks", headers=curator_headers).status_code == 403


# ---------- жизненный цикл ----------

def test_full_lifecycle_student_mode(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers)
    aid = _my_assignment_id(client, curator_headers, task["id"])
    keys = _field_keys(task)

    detail = client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()
    students = _students(db, curator_group)
    assert len(detail["rows"]) == len(students) and detail["can_edit"] and not detail["can_review"]

    # Пока не все ответили — отправить нельзя.
    first = students[0]
    r = client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": [
        {"student_id": first.id, "values": {keys["Кружки"]: ["Спорт", "Танцы"], keys["Телефон родителя"]: "+7 900"}}
    ]})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    r = client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)
    assert r.status_code == 400 and "нет ответа" in r.json()["detail"]

    # Обязательное поле.
    rows = [{"student_id": s.id, "values": {keys["Кружки"]: []}} for s in students]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": rows})
    r = client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)
    assert r.status_code == 400 and "Телефон родителя" in r.json()["detail"]

    rows = [{"student_id": s.id, "values": {keys["Телефон родителя"]: "+7 900"}} for s in students]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": rows})
    r = client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    assert not r.json()["can_edit"]
    assert client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": rows}).status_code == 400

    # Проверяющий (зав. отделением) получил уведомление и видит очередь.
    assert any(n["kind"] == "task_submitted" for n in client.get("/notifications", headers=dept_head_headers).json())
    queue = client.get("/tasks/review-queue", headers=dept_head_headers).json()
    assert [q["id"] for q in queue] == [aid]
    assert client.get(f"/tasks/assignments/{aid}", headers=dept_head_headers).json()["can_review"] is True

    # Возврат требует комментарий; после возврата куратор снова может править.
    review_url = f"/tasks/assignments/{aid}/review"
    assert client.post(review_url, headers=dept_head_headers, json={"action": "return"}).status_code == 400
    r = client.post(review_url, headers=dept_head_headers, json={"action": "return", "comment": "У Иванова нет кружка"})
    assert r.status_code == 200 and r.json()["status"] == "returned" and r.json()["review_comment"]
    assert any(n["kind"] == "task_returned" for n in client.get("/notifications", headers=curator_headers).json())
    assert client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()["can_edit"] is True
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": rows[:1]})
    assert client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()["status"] == "in_progress"
    assert client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers).json()["status"] == "submitted"

    r = client.post(review_url, headers=dept_head_headers, json={"action": "accept"})
    assert r.json()["status"] == "accepted"
    assert any(n["kind"] == "task_accepted" for n in client.get("/notifications", headers=curator_headers).json())
    assert client.post(review_url, headers=dept_head_headers, json={"action": "accept"}).status_code == 400


def test_group_mode_with_link_and_value_validation(client, admin_headers, curator_headers, curator_group, imported):
    fields = [
        {"label": "Видео", "type": "link", "required": True},
        {"label": "Дата съёмки", "type": "date"},
        {"label": "Участников", "type": "number"},
        {"label": "Формат", "type": "select", "options": ["Видео", "Фото"]},
    ]
    task = _create(client, admin_headers, collect_mode="group", fields=fields, title="Видеовизитка")
    aid = _my_assignment_id(client, curator_headers, task["id"])
    keys = _field_keys(task)
    url = f"/tasks/assignments/{aid}/answers"

    for bad in ({"Видео": "не ссылка"}, {"Дата съёмки": "вчера"}, {"Участников": "много"}, {"Формат": "Аудио"}):
        r = client.put(url, headers=curator_headers, json={"group_values": {keys[k]: v for k, v in bad.items()}})
        assert r.status_code == 400, bad
    assert client.put(url, headers=curator_headers, json={"group_values": {"nope": 1}}).status_code == 400
    assert client.put(url, headers=curator_headers, json={"rows": [{"student_id": 1}]}).status_code == 400

    assert client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers).status_code == 400
    r = client.put(url, headers=curator_headers, json={"group_values": {
        keys["Видео"]: "https://vk.com/video1", keys["Участников"]: "12,0", keys["Дата съёмки"]: "2026-10-01"}})
    assert r.status_code == 200 and r.json()["group_values"][keys["Участников"]] == 12
    assert client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers).json()["status"] == "submitted"


def test_selected_mode_only_included_rows_are_checked(client, admin_headers, curator_headers, curator_group, imported, db):
    fields = [{"label": "Тема", "type": "text", "required": True}]
    task = _create(client, admin_headers, collect_mode="selected", fields=fields)
    aid = _my_assignment_id(client, curator_headers, task["id"])
    key = task["fields"][0]["key"]
    a, b = _students(db, curator_group)[:2]
    detail = client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()
    assert all(r["is_included"] is False for r in detail["rows"])

    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": [
        {"student_id": a.id, "is_included": True, "values": {}}, {"student_id": b.id, "is_included": False}]})
    r = client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)
    assert r.status_code == 400 and a.full_name in r.json()["detail"]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": [
        {"student_id": a.id, "is_included": True, "values": {key: "Конкурс"}}]})
    assert client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers).json()["status"] == "submitted"
    # Студент из чужой группы в ответ не попадает.
    other = db.query(Student).filter(Student.study_group_id != curator_group.id).first()
    task2 = _create(client, admin_headers, collect_mode="selected", fields=fields, title="Вторая")
    aid2 = _my_assignment_id(client, curator_headers, task2["id"])
    r = client.put(f"/tasks/assignments/{aid2}/answers", headers=curator_headers,
                   json={"rows": [{"student_id": other.id, "is_included": True}]})
    assert r.status_code == 400


# ---------- правила проверки и права ----------

def _submit_group_task(client, admin_headers, curator_headers, **overrides):
    fields = [{"label": "Сдано", "type": "bool", "required": True}]
    task = _create(client, admin_headers, collect_mode="group", fields=fields, **overrides)
    aid = _my_assignment_id(client, curator_headers, task["id"])
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers,
               json={"group_values": {task["fields"][0]["key"]: True}})
    return task, aid, client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)


def test_reviewer_rule_edu_department(client, admin_headers, dept_head_headers, edu_department_headers, curator_headers, curator_group, imported):
    _, aid, r = _submit_group_task(client, admin_headers, curator_headers, reviewer_rule="edu_department")
    assert r.json()["status"] == "submitted"
    review = f"/tasks/assignments/{aid}/review"
    assert client.post(review, headers=dept_head_headers, json={"action": "accept"}).status_code == 403
    assert client.get("/tasks/review-queue", headers=dept_head_headers).json() == []
    assert len(client.get("/tasks/review-queue", headers=edu_department_headers).json()) == 1
    assert client.post(review, headers=edu_department_headers, json={"action": "accept"}).json()["status"] == "accepted"


def test_reviewer_rule_author_and_none(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported):
    _, aid, r = _submit_group_task(client, dept_head_headers, curator_headers, reviewer_rule="author",
                                   title="От зав. отделением")
    assert r.json()["status"] == "submitted"
    assert client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers,
                       json={"action": "accept"}).json()["status"] == "accepted"

    _, aid2, r2 = _submit_group_task(client, admin_headers, curator_headers, reviewer_rule="none", title="Без проверки")
    assert r2.json()["status"] == "accepted"


def test_access_is_limited_to_assignee_reviewer_and_scoped_managers(
    client, admin_headers, curator_headers, curator_group, db_second_curator, dept_head_headers, imported, db,
):
    task = _create(client, admin_headers)
    aid = _my_assignment_id(client, curator_headers, task["id"])
    from tests.conftest import _login

    other_headers = _login(client, db_second_curator.username, "SecondCurator123!")
    other_group_aid = next(
        a["id"] for a in task["assignments"] if a["study_group_id"] != curator_group.id
    )
    # Куратор не видит назначения чужой группы и не может заполнять чужое.
    assert client.get(f"/tasks/assignments/{other_group_aid}", headers=curator_headers).status_code == 403
    assert client.put(f"/tasks/assignments/{other_group_aid}/answers", headers=curator_headers,
                      json={"rows": []}).status_code == 403
    assert client.get(f"/tasks/assignments/{aid}", headers=other_headers).status_code == 403
    # Зав. отделением видит, но заполнять не может.
    assert client.get(f"/tasks/assignments/{aid}", headers=dept_head_headers).status_code == 200
    assert client.put(f"/tasks/assignments/{aid}/answers", headers=dept_head_headers,
                      json={"rows": []}).status_code == 403


def test_dept_head_of_another_department_sees_nothing(client, admin_headers, imported, db, dept_head_user):
    from app.core.security import hash_password
    from app.models import Role, User
    from tests.conftest import _login

    other = Department(name="Другое")
    db.add(other)
    db.flush()
    role = db.query(Role).filter(Role.code == "dept_head").one()
    db.add(User(username="other_dh", full_name="Чужой зав", role_id=role.id, department_id=other.id,
                password_hash=hash_password("Other123!")))
    db.commit()
    headers = _login(client, "other_dh", "Other123!")
    task = _create(client, admin_headers)
    assert client.get("/tasks", headers=headers).json() == []
    assert client.get(f"/tasks/{task['id']}", headers=headers).status_code == 403
    assert client.get(f"/tasks/{task['id']}/export", headers=headers).status_code == 403
    aid = task["assignments"][0]["id"]
    assert client.get(f"/tasks/assignments/{aid}", headers=headers).status_code == 403


def test_comments_notify_the_other_side(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    _, aid, _ = _submit_group_task(client, admin_headers, curator_headers)
    student = _students(db, curator_group)[0]
    r = client.post(f"/tasks/assignments/{aid}/comments", headers=dept_head_headers,
                    json={"student_id": student.id, "text": "Уточните данные"})
    assert r.status_code == 201
    assert any(n["kind"] == "task_comment" for n in client.get("/notifications", headers=curator_headers).json())
    comments = client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()["comments"]
    assert comments[0]["student_id"] == student.id and comments[0]["text"] == "Уточните данные"


# ---------- просрочка, управление, выгрузка ----------

def test_overdue_flag_and_progress(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers)
    db.query(Task).filter(Task.id == task["id"]).update({"due_date": datetime.date.today() - datetime.timedelta(days=2)})
    db.commit()
    detail = client.get(f"/tasks/{task['id']}", headers=admin_headers).json()
    assert detail["progress"]["overdue"] == detail["progress"]["total"]
    mine = client.get("/tasks/my", headers=curator_headers).json()
    assert mine[0]["is_overdue"] is True
    row = next(t for t in client.get("/tasks", headers=admin_headers).json() if t["id"] == task["id"])
    assert row["progress"]["overdue"] == row["progress"]["total"]


def test_close_update_and_delete_rules(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported):
    task = _create(client, dept_head_headers)
    url = f"/tasks/{task['id']}"
    other = _create(client, admin_headers, title="Чужая")
    assert client.patch(f"/tasks/{other['id']}", headers=dept_head_headers, json={"title": "X"}).status_code == 403
    assert client.patch(url, headers=dept_head_headers, json={"title": "Новое имя"}).json()["title"] == "Новое имя"

    aid = _my_assignment_id(client, curator_headers, task["id"])
    assert client.patch(url, headers=dept_head_headers, json={"is_closed": True}).json()["is_closed"] is True
    r = client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": []})
    assert r.status_code == 400 and "закрыта" in r.json()["detail"]
    client.patch(url, headers=dept_head_headers, json={"is_closed": False})
    assert client.delete(url, headers=admin_headers).status_code == 204  # ответов нет — можно удалить


def test_cannot_delete_task_with_answers(client, admin_headers, curator_headers, curator_group, imported):
    task, aid, _ = _submit_group_task(client, admin_headers, curator_headers)
    r = client.delete(f"/tasks/{task['id']}", headers=admin_headers)
    assert r.status_code == 400
    clean = _create(client, admin_headers, title="Без ответов")
    assert client.delete(f"/tasks/{clean['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/tasks/{clean['id']}", headers=admin_headers).status_code == 404


def test_export_per_student_and_per_group(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers)
    aid = _my_assignment_id(client, curator_headers, task["id"])
    keys = _field_keys(task)
    s = _students(db, curator_group)[0]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": [
        {"student_id": s.id, "values": {keys["Кружки"]: ["Спорт", "Танцы"], keys["Не посещает"]: False,
                                        keys["Телефон родителя"]: "+7 900"}}]})
    r = client.get(f"/tasks/{task['id']}/export", headers=admin_headers)
    assert r.status_code == 200
    rows = list(load_workbook(io.BytesIO(r.content)).worksheets[0].iter_rows(values_only=True))
    assert rows[0][:4] == ("Отделение", "Группа", "Статус", "Студент")
    assert len(rows) == 2  # только студент с ответом
    assert rows[1][1] == curator_group.code and rows[1][3] == s.full_name
    assert rows[1][4] == "Спорт, Танцы" and rows[1][5] == "нет" and rows[1][6] == "+7 900"

    group_task = _create(client, admin_headers, collect_mode="group",
                         fields=[{"label": "Сдано", "type": "bool"}], title="Групповая")
    rows = list(load_workbook(io.BytesIO(client.get(f"/tasks/{group_task['id']}/export", headers=admin_headers).content)).worksheets[0].iter_rows(values_only=True))
    assert rows[0][3] == "Сдано" and len(rows) == 1 + group_task["progress"]["total"]
