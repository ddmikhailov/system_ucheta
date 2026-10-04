"""Шаблоны задач: сохранить задачу как шаблон, увидеть всем, кто создаёт задачи, удалять — автору/админу."""
import datetime

from app.models import AuditLog, TaskTemplate


def _future(days=7):
    return str(datetime.date.today() + datetime.timedelta(days=days))


FIELDS = [
    {"label": "Телефон", "type": "text", "required": True, "dossier_field": "phone"},
    {"label": "Кружки", "type": "multiselect", "options": ["Спорт", "Танцы"]},
]


def _create(client, headers, **over):
    body = {"title": "Контакты студентов", "description": "Проверить телефоны", "collect_mode": "student",
            "reviewer_rule": "dept_head", "due_date": _future(), "fields": FIELDS, "scope": {"all_groups": True}}
    body.update(over)
    r = client.post("/tasks", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _save(client, headers, task_id, name=None):
    return client.post("/tasks/templates", headers=headers, json={"task_id": task_id, "name": name})


def test_task_is_saved_as_a_template_without_due_date(client, admin_headers, curator_group, imported):
    task = _create(client, admin_headers)
    r = _save(client, admin_headers, task["id"], "Ежегодная сверка")
    assert r.status_code == 201
    tpl = r.json()
    assert tpl["name"] == "Ежегодная сверка" and tpl["title"] == "Контакты студентов"
    assert tpl["collect_mode"] == "student" and tpl["reviewer_rule"] == "dept_head"
    assert tpl["scope"]["all_groups"] is True and "due_date" not in tpl
    assert [f["label"] for f in tpl["fields"]] == ["Телефон", "Кружки"]
    assert tpl["fields"][0]["dossier_field"] == "phone" and tpl["fields"][0]["required"] is True
    assert tpl["can_manage"] is True


def test_name_defaults_to_the_task_title(client, admin_headers, curator_group, imported):
    task = _create(client, admin_headers)
    assert _save(client, admin_headers, task["id"]).json()["name"] == "Контакты студентов"
    assert _save(client, admin_headers, task["id"], "   ").json()["name"] == "Контакты студентов"


def test_template_can_be_launched_as_a_new_task(client, admin_headers, curator_group, imported):
    """Запуск = обычное создание из полей шаблона с новым сроком: форма и связь с досье сохраняются."""
    task = _create(client, admin_headers)
    tpl = _save(client, admin_headers, task["id"]).json()
    body = {k: tpl[k] for k in ("title", "description", "collect_mode", "reviewer_rule", "fields", "scope")}
    r = client.post("/tasks", headers=admin_headers, json={**body, "due_date": _future(30)})
    assert r.status_code == 201, r.text
    again = r.json()
    assert again["id"] != task["id"] and again["due_date"] == _future(30)
    assert [(f["label"], f.get("dossier_field")) for f in again["fields"]] == [("Телефон", "phone"), ("Кружки", None)]


def test_templates_are_listed_for_task_managers_only(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported):
    task = _create(client, admin_headers)
    _save(client, admin_headers, task["id"], "Б-шаблон")
    _save(client, admin_headers, task["id"], "А-шаблон")
    names = [t["name"] for t in client.get("/tasks/templates", headers=dept_head_headers).json()]
    assert names == ["А-шаблон", "Б-шаблон"]  # шаблоны общие, по алфавиту
    assert client.get("/tasks/templates", headers=curator_headers).status_code == 403
    assert client.post("/tasks/templates", headers=curator_headers, json={"task_id": task["id"]}).status_code == 403


def test_only_author_or_admin_deletes(client, admin_headers, dept_head_headers, edu_department_headers, curator_group, imported, db):
    task = _create(client, dept_head_headers)
    tpl = _save(client, dept_head_headers, task["id"], "Мой").json()
    url = f"/tasks/templates/{tpl['id']}"
    seen = {t["id"]: t for t in client.get("/tasks/templates", headers=edu_department_headers).json()}
    assert seen[tpl["id"]]["can_manage"] is False
    assert client.delete(url, headers=edu_department_headers).status_code == 403
    assert client.delete(url, headers=dept_head_headers).status_code == 204
    assert client.delete(url, headers=dept_head_headers).status_code == 404

    other = _save(client, dept_head_headers, task["id"], "Другой").json()
    assert client.delete(f"/tasks/templates/{other['id']}", headers=admin_headers).status_code == 204
    assert db.query(TaskTemplate).count() == 0
    actions = [a.action for a in db.query(AuditLog).filter(AuditLog.action.like("task.template_%"))]
    assert actions.count("task.template_create") == 2 and actions.count("task.template_delete") == 2


def test_cannot_save_someone_elses_task_as_a_template(client, admin_headers, dept_head_headers, curator_group, imported, db):
    from app.models import Department, StudyGroup

    other_dept = Department(name="Другое отделение")
    db.add(other_dept)
    db.flush()
    group = StudyGroup(code="ДР101", course=1, department_id=other_dept.id, is_active=True)
    db.add(group)
    db.commit()
    task = _create(client, admin_headers, scope={"group_ids": [group.id]})
    assert _save(client, dept_head_headers, task["id"]).status_code == 403
    assert _save(client, admin_headers, 99999).status_code == 404
