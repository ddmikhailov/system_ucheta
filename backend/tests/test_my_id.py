"""Вкладка «Мой ID»: биометрия и чаты MAX по студентам группы; выдуманные данные."""
from app.models import AuditLog, GroupEvent, GroupEventAttendee, ParentMeeting, ParentMeetingAttendee, Student, StudentGuardian, StudentMyId, StudyGroup
from app.services import erasure_service


def _students(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).order_by(Student.last_name, Student.first_name).all()


def _url(group, year=None):
    return f"/my-id/groups/{group.id}" + (f"?year={year}" if year else "")


def _row(student, **over):
    return {"student_id": student.id, **over}


def test_empty_table_lists_the_whole_group_with_nothing_filled(client, curator_headers, curator_group, db):
    data = client.get(_url(curator_group), headers=curator_headers).json()
    students = _students(db, curator_group)
    assert [r["student_id"] for r in data["rows"]] == [s.id for s in students]
    assert all(r["biometrics"] is None and r["max_student"] is None and r["max_parent"] is None for r in data["rows"])
    assert data["totals"] == {"students": len(students), "biometrics_yes": 0, "biometrics_no": 0, "biometrics_unset": len(students),
                              "max_student_yes": 0, "max_student_no": 0, "max_parent_yes": 0, "max_parent_no": 0}
    assert data["can_edit"] is True and data["group_code"] == curator_group.code and len(data["school_year"]) == 9


def test_save_and_totals_reason_kept_only_for_no(client, curator_headers, curator_group, db):
    a, b, c = _students(db, curator_group)[:3]
    r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [
        _row(a, biometrics=True, biometrics_reason="лишняя причина", max_student=True, max_parent=False, max_parent_reason="  нет аккаунта  "),
        _row(b, biometrics=False, biometrics_reason="тех. трудности, айфон", max_student=False, max_student_reason="не пользуется"),
        _row(c),  # ничего не отмечено — запись не создаётся
    ]})
    assert r.status_code == 200, r.text
    rows = {x["student_id"]: x for x in r.json()["rows"]}
    assert rows[a.id]["biometrics"] is True and rows[a.id]["biometrics_reason"] is None  # при «ДА» причина стирается
    assert rows[a.id]["max_parent"] is False and rows[a.id]["max_parent_reason"] == "нет аккаунта"
    assert rows[b.id]["biometrics_reason"] == "тех. трудности, айфон" and rows[b.id]["max_student_reason"] == "не пользуется"
    assert rows[c.id]["biometrics"] is None
    totals = r.json()["totals"]
    assert (totals["biometrics_yes"], totals["biometrics_no"], totals["biometrics_unset"]) == (1, 1, len(rows) - 2)
    assert (totals["max_student_yes"], totals["max_student_no"], totals["max_parent_no"]) == (1, 1, 1)
    assert db.query(StudentMyId).count() == 2  # для c записи нет


def test_partial_save_does_not_touch_other_students(client, curator_headers, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=True), _row(b, biometrics=False, biometrics_reason="x")]})
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, max_student=True)]})  # другой показатель того же студента
    rows = {x["student_id"]: x for x in client.get(_url(curator_group), headers=curator_headers).json()["rows"]}
    assert rows[a.id]["biometrics"] is True and rows[a.id]["max_student"] is True
    assert rows[b.id]["biometrics"] is False and rows[b.id]["biometrics_reason"] == "x"  # b не присылали — не тронут
    assert db.query(StudentMyId).filter_by(student_id=a.id).count() == 1


def test_an_answer_cannot_be_changed_once_saved(client, curator_headers, admin_headers, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=True, max_student=False), _row(b, biometrics=False)]})

    for flipped in ({"biometrics": False}, {"max_student": True}):
        r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, **flipped)]})
        assert r.status_code == 409 and "исправить" in r.json()["detail"]
    # конфликт в одной строке отменяет всю отправку: вторая строка не сохраняется
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=True), _row(b, max_parent=True)]})
    r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(b, max_parent=False), _row(a, biometrics=False)]})
    assert r.status_code == 409
    rows = {x["student_id"]: x for x in client.get(_url(curator_group), headers=curator_headers).json()["rows"]}
    assert rows[a.id]["biometrics"] is True and rows[a.id]["max_student"] is False
    assert rows[b.id]["max_parent"] is True  # осталось как сохранено до конфликтной отправки

    # то же значение — не конфликт; пустое значение — «не менять», а не сброс
    same = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=True)]})
    assert same.status_code == 200
    cleared = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a)]})
    assert cleared.status_code == 200
    rows = {x["student_id"]: x for x in cleared.json()["rows"]}
    assert rows[a.id]["biometrics"] is True and rows[a.id]["max_student"] is False
    # то же — у администрации: исправить нельзя никому
    assert client.put(_url(curator_group), headers=admin_headers, json={"rows": [_row(a, biometrics=False)]}).status_code == 409


def test_reason_can_be_added_or_edited_after_no_but_never_after_yes(client, curator_headers, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=False), _row(b, biometrics=True)]})
    r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=False, biometrics_reason="  нет смартфона ")]})
    assert {x["student_id"]: x for x in r.json()["rows"]}[a.id]["biometrics_reason"] == "нет смартфона"
    r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics_reason="поправлено")]})  # ответ не присылали
    assert {x["student_id"]: x for x in r.json()["rows"]}[a.id]["biometrics_reason"] == "поправлено"
    r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=False, biometrics_reason="")]})
    assert {x["student_id"]: x for x in r.json()["rows"]}[a.id]["biometrics_reason"] is None  # пустую прислали — стёрли
    r = client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(b, biometrics=True, biometrics_reason="лишняя")]})
    assert {x["student_id"]: x for x in r.json()["rows"]}[b.id]["biometrics_reason"] is None  # при «Да» причины нет


def test_school_years_are_separate(client, curator_headers, curator_group, db):
    a = _students(db, curator_group)[0]
    client.put(_url(curator_group, "2025-2026"), headers=curator_headers, json={"rows": [_row(a, biometrics=True)]})
    old = {x["student_id"]: x for x in client.get(_url(curator_group, "2025-2026"), headers=curator_headers).json()["rows"]}
    current = {x["student_id"]: x for x in client.get(_url(curator_group), headers=curator_headers).json()["rows"]}
    assert old[a.id]["biometrics"] is True and current[a.id]["biometrics"] is None


def test_validation(client, curator_headers, admin_headers, curator_group, db):
    a = _students(db, curator_group)[0]
    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    foreign = db.query(Student).filter_by(study_group_id=other_group.id).first()
    put = lambda rows, **kw: client.put(_url(curator_group, kw.get("year")), headers=curator_headers, json={"rows": rows})  # noqa: E731
    assert put([_row(foreign, biometrics=True)]).status_code == 400
    assert put([_row(a, biometrics=True), _row(a, biometrics=False)]).status_code == 400
    assert put([_row(a, biometrics=False, biometrics_reason="я" * 256)]).status_code == 422
    assert put([{"student_id": a.id, "biometrics": "maybe"}]).status_code == 422
    assert put([], year="2026").status_code == 422
    assert client.get(_url(curator_group, "2026"), headers=curator_headers).status_code == 422
    assert client.get("/my-id/groups/999999", headers=admin_headers).status_code == 404


def test_access_rules(client, curator_headers, admin_headers, curator_group, db):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    student = _students(db, other)[0]
    assert client.get(_url(curator_group)).status_code == 401
    assert client.get(_url(other), headers=curator_headers).status_code == 403
    assert client.put(_url(other), headers=curator_headers, json={"rows": []}).status_code == 403
    assert client.get(_url(other), headers=admin_headers).status_code == 200
    saved = client.put(_url(other), headers=admin_headers, json={"rows": [_row(student, max_parent=True)]})
    assert saved.status_code == 200 and saved.json()["can_edit"] is True


def test_save_is_audited_with_counts_only(client, curator_headers, curator_user, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=False, biometrics_reason="секретная-причина"), _row(b, biometrics=True)]})
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=False, biometrics_reason="секретная-причина")]})  # без изменений
    entries = db.query(AuditLog).filter(AuditLog.action == "my_id.save", AuditLog.user_id == curator_user.id).order_by(AuditLog.id).all()
    assert [e.new_value.split(":")[1] for e in entries] == ["2", "0"]
    assert all("секретная" not in (e.new_value or "") for e in entries)


def test_erasing_a_student_removes_my_id_and_attendance_records(client, curator_headers, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=True)]})
    event = client.post(f"/events/groups/{curator_group.id}", headers=curator_headers, json={"section": "group_org", "title": "Час", "is_class_hour": True}).json()
    client.put(f"/events/{event['id']}/attendance", headers=curator_headers, json={"student_ids": [a.id, b.id]})
    client.post(f"/students/{a.id}/dossier/guardians", headers=curator_headers, json={"full_name": "Мать А.", "relation": "мать"})
    guardian = db.query(StudentGuardian).filter_by(student_id=a.id).one()
    meeting = client.post(f"/meetings/groups/{curator_group.id}", headers=curator_headers, json={}).json()
    client.put(f"/meetings/{meeting['id']}/attendance", headers=curator_headers, json={"guardian_ids": [guardian.id]})

    erasure_service.erase_student_personal_data(db, [a.id], include_access_log=True)
    db.commit()
    assert db.query(StudentMyId).filter_by(student_id=a.id).count() == 0
    assert [x.student_id for x in db.query(GroupEventAttendee).filter_by(event_id=event["id"])] == [b.id]  # студент b остался
    assert db.query(ParentMeetingAttendee).filter_by(meeting_id=meeting["id"]).count() == 0


def test_deleting_a_group_removes_its_plan_meetings_and_reports(client, admin_headers, curator_headers, curator_group, db):
    group_id = curator_group.id
    a = _students(db, curator_group)[0]
    client.put(_url(curator_group), headers=curator_headers, json={"rows": [_row(a, biometrics=True)]})
    event = client.post(f"/events/groups/{group_id}", headers=curator_headers, json={"section": "group_org", "title": "Час", "is_class_hour": True}).json()
    client.put(f"/events/{event['id']}/attendance", headers=curator_headers, json={"student_ids": [a.id]})
    meeting = client.post(f"/meetings/groups/{group_id}", headers=curator_headers, json={}).json()
    client.put(f"/reports/groups/{group_id}", headers=curator_headers, json={"values": {"g_iup": "2"}})

    r = client.delete(f"/admin/groups/{group_id}?force=true&confirm_code={curator_group.code}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert db.query(GroupEvent).filter_by(study_group_id=group_id).count() == 0
    assert db.query(GroupEventAttendee).count() == 0 and db.query(ParentMeeting).filter_by(id=meeting["id"]).count() == 0
    assert db.query(StudentMyId).count() == 0
