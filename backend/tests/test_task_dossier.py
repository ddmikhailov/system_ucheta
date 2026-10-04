"""Связь задач с досье: привязка поля формы к полю досье, запись при приёмке, подстановка в форму."""
import datetime

from app.models import AuditLog, Student, StudentNote, StudentProfile


def _future(days=7):
    return str(datetime.date.today() + datetime.timedelta(days=days))


def _payload(fields, **overrides):
    base = {
        "title": "Актуализация контактов", "description": None, "collect_mode": "student",
        "reviewer_rule": "dept_head", "due_date": _future(), "fields": fields, "scope": {"all_groups": True},
    }
    base.update(overrides)
    return base


PHONE = {"label": "Телефон", "type": "text", "dossier_field": "phone"}
CIRCLES = {"label": "Кружки", "type": "multiselect", "options": ["Спорт", "Танцы"], "dossier_field": "additional_education"}


def _create(client, headers, fields, **overrides):
    return client.post("/tasks", headers=headers, json=_payload(fields, **overrides))


def _assignment_id(client, headers, task_id):
    return next(r["id"] for r in client.get("/tasks/my", headers=headers).json() if r["task_id"] == task_id)


def _students(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).all()


def _fill_and_submit(client, headers, aid, students, values_by_index):
    rows = [{"student_id": s.id, "values": values_by_index.get(i, {})} for i, s in enumerate(students)]
    assert client.put(f"/tasks/assignments/{aid}/answers", headers=headers, json={"rows": rows}).status_code == 200
    return client.post(f"/tasks/assignments/{aid}/submit", headers=headers)


def _profile(db, student_id):
    db.expire_all()
    return db.get(StudentProfile, student_id)


# ---------- создание ----------

def test_dossier_targets_endpoint_lists_only_ordinary_fields(client, admin_headers, curator_headers):
    r = client.get("/tasks/dossier-fields", headers=admin_headers)
    assert r.status_code == 200
    keys = {t["key"] for t in r.json()}
    assert {"phone", "email", "birth_date", "funding", "additional_education"} <= keys
    assert not keys & {"is_orphan", "has_ovz", "pdn_kdn", "health_note", "special"}  # особые данные не привязываются
    assert client.get("/tasks/dossier-fields", headers=curator_headers).status_code == 403


def test_link_is_stored_in_the_form(client, admin_headers, curator_group, imported):
    r = _create(client, admin_headers, [PHONE])
    assert r.status_code == 201
    assert r.json()["fields"][0]["dossier_field"] == "phone"


def test_invalid_links_are_rejected(client, admin_headers, curator_group, imported):
    cases = [
        ([{"label": "Здоровье", "type": "text", "dossier_field": "health_note"}], {}, "нет поля"),
        ([{"label": "Телефон", "type": "number", "dossier_field": "phone"}], {}, "подходит тип"),
        ([PHONE, {"label": "Ещё телефон", "type": "text", "dossier_field": "phone"}], {}, "Два поля"),
        ([PHONE], {"collect_mode": "group"}, "только в задачах по студентам"),
        ([{"label": "Фин.", "type": "select", "options": ["бюджет", "платно"], "dossier_field": "funding"}], {}, "бюджет"),
    ]
    for fields, over, text in cases:
        r = _create(client, admin_headers, fields, **over)
        assert r.status_code == 400 and text in r.json()["detail"], (text, r.text)


# ---------- запись при приёмке ----------

def test_accepted_answers_are_written_to_the_dossier(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, [PHONE, CIRCLES]).json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    keys = {f["label"]: f["key"] for f in task["fields"]}
    r = _fill_and_submit(client, curator_headers, aid, students, {
        0: {keys["Телефон"]: "+7 900 111-22-33", keys["Кружки"]: ["Спорт", "Танцы"]},
        1: {keys["Телефон"]: "+7 900 444-55-66"},
    })
    assert r.json()["status"] == "submitted"
    assert _profile(db, students[0].id) is None or _profile(db, students[0].id).phone is None  # до приёмки — ничего

    r = client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "accept"})
    assert r.json()["status"] == "accepted"
    first, second = _profile(db, students[0].id), _profile(db, students[1].id)
    assert first.phone == "+7 900 111-22-33" and first.additional_education == "Спорт, Танцы"
    assert second.phone == "+7 900 444-55-66" and second.additional_education is None
    # студент без ответов не затронут
    third = _profile(db, students[2].id) if len(students) > 2 else None
    assert third is None or third.phone is None


def test_return_does_not_touch_the_dossier(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, [PHONE]).json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    _fill_and_submit(client, curator_headers, aid, students, {0: {task["fields"][0]["key"]: "+7 900 000-00-00"}})
    client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "return", "comment": "поправьте"})
    profile = _profile(db, students[0].id)
    assert profile is None or profile.phone is None


def test_empty_answers_do_not_erase_the_dossier(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    students = _students(db, curator_group)
    db.add(StudentProfile(student_id=students[0].id, phone="+7 111", email="old@example.com"))
    db.commit()
    task = _create(client, admin_headers, [PHONE, {"label": "Почта", "type": "text", "dossier_field": "email"}]).json()
    keys = {f["label"]: f["key"] for f in task["fields"]}
    aid = _assignment_id(client, curator_headers, task["id"])
    _fill_and_submit(client, curator_headers, aid, students, {0: {keys["Почта"]: "new@example.com"}, 1: {keys["Телефон"]: "+7 222"}})
    client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "accept"})
    first = _profile(db, students[0].id)
    assert first.email == "new@example.com" and first.phone == "+7 111"  # телефон не стёрт пустым ответом


def test_dossier_update_leaves_a_trail_without_values(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, [PHONE]).json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    _fill_and_submit(client, curator_headers, aid, students, {0: {task["fields"][0]["key"]: "+7 900 777-88-99"}})
    client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "accept"})
    note = db.query(StudentNote).filter(StudentNote.student_id == students[0].id).one()
    assert f"№{task['id']}" in note.text and "Телефон студента" in note.text
    entry = db.query(AuditLog).filter(AuditLog.action == "dossier.task_update").one()
    assert entry.entity_id == str(students[0].id) and entry.new_value == f"task:{task['id']}:phone"
    assert "900" not in note.text and "900" not in entry.new_value  # номер в след не попадает
    # карточка студента показывает заметку
    shown = client.get(f"/students/{students[0].id}/dossier", headers=dept_head_headers).json()
    assert shown["profile"]["phone"] == "+7 900 777-88-99"
    assert any(f"№{task['id']}" in n["text"] for n in shown["notes"])


def test_task_without_review_writes_on_submit(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, [PHONE], reviewer_rule="none").json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    r = _fill_and_submit(client, curator_headers, aid, students, {0: {task["fields"][0]["key"]: "+7 900 123-45-67"}})
    assert r.json()["status"] == "accepted"
    assert _profile(db, students[0].id).phone == "+7 900 123-45-67"


def test_two_step_review_writes_only_after_the_final_step(client, admin_headers, dept_head_headers, edu_department_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, [PHONE], reviewer_rule="two_step").json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    _fill_and_submit(client, curator_headers, aid, students, {0: {task["fields"][0]["key"]: "+7 900 555-00-11"}})
    client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "accept"})
    profile = _profile(db, students[0].id)
    assert profile is None or profile.phone is None  # первая ступень — ещё не принято
    client.post(f"/tasks/assignments/{aid}/review", headers=edu_department_headers, json={"action": "accept"})
    assert _profile(db, students[0].id).phone == "+7 900 555-00-11"


def test_funding_and_birth_date_are_converted(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    fields = [{"label": "Финансирование", "type": "select", "options": ["бюджет", "договор"], "dossier_field": "funding"},
              {"label": "Дата рождения", "type": "date", "dossier_field": "birth_date"}]
    task = _create(client, admin_headers, fields).json()
    keys = {f["label"]: f["key"] for f in task["fields"]}
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    _fill_and_submit(client, curator_headers, aid, students, {0: {keys["Финансирование"]: "договор", keys["Дата рождения"]: "2008-05-17"}})
    client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "accept"})
    profile = _profile(db, students[0].id)
    assert profile.funding == "contract" and profile.birth_date == datetime.date(2008, 5, 17)


# ---------- проверка длины и подстановка ----------

def test_answer_too_long_for_the_dossier_field_is_rejected_when_saving(client, admin_headers, curator_headers, curator_group, imported, db):
    task = _create(client, admin_headers, [PHONE]).json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    r = client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers,
                   json={"rows": [{"student_id": students[0].id, "values": {task["fields"][0]["key"]: "9" * 40}}]})
    assert r.status_code == 400 and "максимум 32" in r.json()["detail"]


def test_form_opens_prefilled_from_the_dossier_for_the_curator_only(client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db):
    students = _students(db, curator_group)
    db.add(StudentProfile(student_id=students[0].id, phone="+7 900 000-11-22", additional_education="Спорт"))
    db.commit()
    task = _create(client, admin_headers, [PHONE, CIRCLES]).json()
    keys = {f["label"]: f["key"] for f in task["fields"]}
    aid = _assignment_id(client, curator_headers, task["id"])

    rows = {r["student_id"]: r for r in client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()["rows"]}
    assert rows[students[0].id]["values"] == {keys["Телефон"]: "+7 900 000-11-22", keys["Кружки"]: ["Спорт"]}
    assert rows[students[1].id]["values"] == {}

    # проверяющий видит только то, что реально сохранил куратор
    seen = {r["student_id"]: r for r in client.get(f"/tasks/assignments/{aid}", headers=dept_head_headers).json()["rows"]}
    assert seen[students[0].id]["values"] == {}


def test_saved_answers_win_over_the_dossier(client, admin_headers, curator_headers, curator_group, imported, db):
    students = _students(db, curator_group)
    db.add(StudentProfile(student_id=students[0].id, phone="+7 old"))
    db.commit()
    task = _create(client, admin_headers, [PHONE]).json()
    key = task["fields"][0]["key"]
    aid = _assignment_id(client, curator_headers, task["id"])
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers,
               json={"rows": [{"student_id": students[0].id, "values": {key: "+7 new"}}]})
    rows = {r["student_id"]: r for r in client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()["rows"]}
    assert rows[students[0].id]["values"] == {key: "+7 new"}


def test_multiselect_is_not_prefilled_when_the_dossier_has_other_text(client, admin_headers, curator_headers, curator_group, imported, db):
    """«Шахматы, Спорт» — «Шахмат» нет в вариантах; подстановка только «Спорт» затёрла бы остальное при сохранении."""
    students = _students(db, curator_group)
    db.add(StudentProfile(student_id=students[0].id, additional_education="Шахматы, Спорт"))
    db.commit()
    task = _create(client, admin_headers, [CIRCLES]).json()
    aid = _assignment_id(client, curator_headers, task["id"])
    rows = {r["student_id"]: r for r in client.get(f"/tasks/assignments/{aid}", headers=curator_headers).json()["rows"]}
    assert rows[students[0].id]["values"] == {}
