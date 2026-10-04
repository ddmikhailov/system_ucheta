"""Многошаговые задачи: шаг 2 создаётся «после» шага 1 и открывается, когда предыдущий шаг сдан/принят."""
import datetime

from app.models import Department, StudyGroup, Task, TaskAssignment

FIELDS = [{"label": "Готово", "type": "bool", "required": True}]


def _day(days):
    return str(datetime.date.today() + datetime.timedelta(days=days))


def _body(title, due=5, **over):
    body = {"title": title, "description": None, "collect_mode": "group", "reviewer_rule": "dept_head",
            "due_date": _day(due), "fields": FIELDS, "scope": {"all_groups": True}}
    body.update(over)
    return body


def _step1(client, headers, **over):
    r = client.post("/tasks", headers=headers, json=_body("Сценарий видеовизитки", **over))
    assert r.status_code == 201, r.text
    return r.json()


def _step2(client, headers, after, **over):
    due = over.pop("due", 15)
    return client.post("/tasks", headers=headers, json=_body("Видеовизитка", due=due, after_task_id=after, **over))


def _mine(client, headers, task_id):
    return next(r for r in client.get("/tasks/my", headers=headers).json() if r["task_id"] == task_id)


def _submit(client, headers, aid):
    key = client.get(f"/tasks/assignments/{aid}", headers=headers).json()["fields"][0]["key"]
    client.put(f"/tasks/assignments/{aid}/answers", headers=headers, json={"group_values": {key: True}})
    return client.post(f"/tasks/assignments/{aid}/submit", headers=headers)


def _kinds(client, headers):
    return [n["message"] for n in client.get("/notifications", headers=headers).json() if n["kind"] == "task_assigned"]


def test_second_step_is_locked_until_the_first_is_accepted(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported):
    one = _step1(client, admin_headers)
    r = _step2(client, admin_headers, one["id"])
    assert r.status_code == 201, r.text
    two = r.json()
    assert two["step_no"] == 2 and [s["step_no"] for s in two["steps"]] == [1, 2]
    a1, a2 = _mine(client, curator_headers, one["id"]), _mine(client, curator_headers, two["id"])
    assert a1["is_locked"] is False and a1["step_total"] == 2 and a2["is_locked"] is True and a2["step_no"] == 2

    # закрытый шаг: правка запрещена, причина понятна; уведомления о нём куратору нет
    detail = client.get(f"/tasks/assignments/{a2['id']}", headers=curator_headers).json()
    assert detail["is_locked"] and detail["can_edit"] is False and "Сценарий видеовизитки" in detail["locked_reason"]
    assert client.put(f"/tasks/assignments/{a2['id']}/answers", headers=curator_headers, json={"group_values": {}}).status_code == 400
    assert not any("Видеовизитка" in m for m in _kinds(client, curator_headers))

    # сдан, но не принят — для правила «после приёмки» ещё закрыт
    assert _submit(client, curator_headers, a1["id"]).json()["status"] == "submitted"
    assert _mine(client, curator_headers, two["id"])["is_locked"] is True
    client.post(f"/tasks/assignments/{a1['id']}/review", headers=dept_head_headers, json={"action": "accept"})
    opened = _mine(client, curator_headers, two["id"])
    assert opened["is_locked"] is False
    assert any("Открыт следующий шаг «Видеовизитка»" in m for m in _kinds(client, curator_headers))
    assert _submit(client, curator_headers, opened["id"]).json()["status"] == "submitted"


def test_unlock_on_submit_rule(client, admin_headers, curator_headers, curator_group, imported):
    one = _step1(client, admin_headers)
    two = _step2(client, admin_headers, one["id"], unlock_on="submitted").json()
    assert two["unlock_on"] == "submitted"
    a1 = _mine(client, curator_headers, one["id"])
    assert _mine(client, curator_headers, two["id"])["is_locked"] is True
    _submit(client, curator_headers, a1["id"])
    assert _mine(client, curator_headers, two["id"])["is_locked"] is False  # хватило сдачи


def test_task_without_review_unlocks_on_submit_even_with_accepted_rule(client, admin_headers, curator_headers, curator_group, imported):
    one = _step1(client, admin_headers, reviewer_rule="none")
    two = _step2(client, admin_headers, one["id"]).json()
    r = _submit(client, curator_headers, _mine(client, curator_headers, one["id"])["id"])
    assert r.json()["status"] == "accepted"  # сразу принято → следующий шаг открыт
    assert _mine(client, curator_headers, two["id"])["is_locked"] is False


def test_returned_first_step_keeps_the_second_locked_and_does_not_relock_opened_ones(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported):
    one = _step1(client, admin_headers)
    two = _step2(client, admin_headers, one["id"], unlock_on="submitted").json()
    a1 = _mine(client, curator_headers, one["id"])
    _submit(client, curator_headers, a1["id"])
    client.post(f"/tasks/assignments/{a1['id']}/review", headers=dept_head_headers, json={"action": "return", "comment": "доработать"})
    assert _mine(client, curator_headers, two["id"])["is_locked"] is False  # уже открыт, возврат его не закрывает


def test_step_inherits_scope_and_can_only_extend_the_last_step(client, admin_headers, curator_group, imported, db):
    one = _step1(client, admin_headers, scope={"group_ids": [curator_group.id]})
    two = _step2(client, admin_headers, one["id"], scope={"all_groups": True}).json()  # scope игнорируется
    assert two["scope"]["group_ids"] == [curator_group.id] and two["scope"]["all_groups"] is False
    assert [a["group_code"] for a in two["assignments"]] == [curator_group.code]
    again = _step2(client, admin_headers, one["id"])
    assert again.status_code == 400 and "следующий" in again.json()["detail"]
    third = client.post("/tasks", headers=admin_headers, json=_body("Шаг 3", due=25, after_task_id=two["id"]))
    assert third.status_code == 201 and third.json()["step_no"] == 3 and len(third.json()["steps"]) == 3


def test_step_rules_due_date_rights_and_missing_predecessor(client, admin_headers, dept_head_headers, curator_group, imported):
    one = _step1(client, admin_headers, due=10)
    early = client.post("/tasks", headers=admin_headers, json=_body("Раньше", due=3, after_task_id=one["id"]))
    assert early.status_code == 400 and "раньше" in early.json()["detail"]
    assert client.post("/tasks", headers=dept_head_headers, json=_body("Чужой", due=20, after_task_id=one["id"])).status_code == 403
    assert client.post("/tasks", headers=admin_headers, json=_body("Нет", due=20, after_task_id=99999)).status_code == 404


def test_deleting_steps_goes_from_the_last_one(client, admin_headers, curator_group, imported, db):
    one = _step1(client, admin_headers)
    two = _step2(client, admin_headers, one["id"]).json()
    middle = client.delete(f"/tasks/{one['id']}", headers=admin_headers)
    assert middle.status_code == 400 and "следующий шаг" in middle.json()["detail"]
    assert client.delete(f"/tasks/{two['id']}", headers=admin_headers).status_code == 204
    assert client.delete(f"/tasks/{one['id']}", headers=admin_headers).status_code == 204
    assert db.query(Task).count() == 0


def test_list_marks_steps_and_single_tasks_have_no_step_total(client, admin_headers, curator_group, imported):
    single = _step1(client, admin_headers)
    chain1 = client.post("/tasks", headers=admin_headers, json=_body("Цепочка", due=5)).json()
    chain2 = client.post("/tasks", headers=admin_headers, json=_body("Цепочка 2", due=9, after_task_id=chain1["id"])).json()
    rows = {r["id"]: r for r in client.get("/tasks", headers=admin_headers).json()}
    assert rows[single["id"]]["step_total"] is None
    assert (rows[chain1["id"]]["step_no"], rows[chain1["id"]]["step_total"]) == (1, 2)
    assert (rows[chain2["id"]]["step_no"], rows[chain2["id"]]["step_total"]) == (2, 2)


def test_locked_step_has_no_reminders_and_is_not_overdue(client, admin_headers, curator_headers, curator_group, imported, db):
    from app.services import task_service

    one = _step1(client, admin_headers, due=30)
    two = _step2(client, admin_headers, one["id"], due=40).json()
    db.query(Task).filter(Task.id == two["id"]).update({"due_date": datetime.date.today() - datetime.timedelta(days=2)})
    db.commit()
    task_service.reset_reminder_throttle()
    client.get("/notifications/unread-count", headers=curator_headers)
    kinds = [n["kind"] for n in client.get("/notifications", headers=curator_headers).json()]
    assert "task_overdue" not in kinds
    assert _mine(client, curator_headers, two["id"])["is_overdue"] is False


def test_group_added_later_gets_a_step_only_together_with_the_previous_one(client, admin_headers, curator_group, imported, db):
    from app.services import task_service

    one = _step1(client, admin_headers)
    two = _step2(client, admin_headers, one["id"]).json()
    dept = db.get(Department, curator_group.department_id)
    group = StudyGroup(code="НОВ101", course=1, department_id=dept.id, is_active=True)
    db.add(group)
    db.flush()
    assert task_service.assign_new_group(db, group) == 2
    db.commit()
    by_task = {a.task_id: a for a in db.query(TaskAssignment).filter(TaskAssignment.study_group_id == group.id)}
    assert by_task[one["id"]].locked is False and by_task[two["id"]].locked is True
