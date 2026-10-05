"""Заполненность назначения в «Моих задачах» (этап 13): полоска «18 из 25» и замечание при возврате."""
from tests.test_tasks import _create, _field_keys, _my_assignment_id, _students


def _my_row(client, headers, task_id):
    return next(r for r in client.get("/tasks/my", headers=headers).json() if r["task_id"] == task_id)


def test_student_mode_counts_rows_with_required_fields(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers)  # обязательное поле — «Телефон родителя»
    keys = _field_keys(task)
    students = _students(db, curator_group)
    row = _my_row(client, curator_headers, task["id"])
    assert (row["filled"], row["total"]) == (0, len(students))

    aid = row["id"]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": [
        {"student_id": students[0].id, "values": {keys["Телефон родителя"]: "+7 900"}},
        # Кружок выбран, но обязательного телефона нет — строка не считается заполненной.
        {"student_id": students[1].id, "values": {keys["Кружки"]: ["Спорт"]}},
    ]})
    row = _my_row(client, curator_headers, task["id"])
    assert (row["filled"], row["total"]) == (1, len(students))


def test_without_required_fields_any_value_counts(client, admin_headers, curator_headers, curator_group, imported, db):
    fields = [{"label": "Кружки", "type": "multiselect", "options": ["Спорт"]}, {"label": "Не посещает", "type": "bool"}]
    task = _create(client, admin_headers, fields=fields)
    keys = _field_keys(task)
    a, b = _students(db, curator_group)[:2]
    aid = _my_assignment_id(client, curator_headers, task["id"])
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"rows": [
        {"student_id": a.id, "values": {keys["Не посещает"]: False}},
        {"student_id": b.id, "values": {keys["Кружки"]: []}},
    ]})
    assert _my_row(client, curator_headers, task["id"])["filled"] == 1


def test_group_mode_counts_fields(client, admin_headers, curator_headers, curator_group, imported):
    fields = [{"label": "Видео", "type": "link", "required": True}, {"label": "Участников", "type": "number"}]
    task = _create(client, admin_headers, collect_mode="group", fields=fields, title="Видеовизитка")
    keys = _field_keys(task)
    row = _my_row(client, curator_headers, task["id"])
    assert (row["filled"], row["total"]) == (0, 2)
    client.put(f"/tasks/assignments/{row['id']}/answers", headers=curator_headers,
               json={"group_values": {keys["Видео"]: "https://vk.com/video1"}})
    assert _my_row(client, curator_headers, task["id"])["filled"] == 1


def test_selected_mode_counts_only_chosen_students(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, collect_mode="selected", fields=[{"label": "Тема", "type": "text", "required": True}])
    key = task["fields"][0]["key"]
    a, b, c = _students(db, curator_group)[:3]
    row = _my_row(client, curator_headers, task["id"])
    assert (row["filled"], row["total"]) == (0, 0)
    client.put(f"/tasks/assignments/{row['id']}/answers", headers=curator_headers, json={"rows": [
        {"student_id": a.id, "is_included": True, "values": {key: "Конкурс"}},
        {"student_id": b.id, "is_included": True, "values": {}},
        {"student_id": c.id, "is_included": False, "values": {key: "не считается"}},
    ]})
    row = _my_row(client, curator_headers, task["id"])
    assert (row["filled"], row["total"]) == (1, 2)


def test_review_comment_is_shown_only_while_returned(
    client, admin_headers, dept_head_headers, curator_headers, curator_group, imported,
):
    task = _create(client, admin_headers, collect_mode="group", fields=[{"label": "Сдано", "type": "bool", "required": True}])
    aid = _my_assignment_id(client, curator_headers, task["id"])
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"group_values": {task["fields"][0]["key"]: True}})
    client.post(f"/tasks/assignments/{aid}/submit", headers=curator_headers)
    assert _my_row(client, curator_headers, task["id"])["review_comment"] is None

    client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "return", "comment": "Добавьте фото"})
    row = _my_row(client, curator_headers, task["id"])
    assert row["status"] == "returned" and row["review_comment"] == "Добавьте фото"

    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers, json={"group_values": {task["fields"][0]["key"]: True}})
    assert _my_row(client, curator_headers, task["id"])["review_comment"] is None
