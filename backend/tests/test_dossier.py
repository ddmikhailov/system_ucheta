"""Досье студента (futures.md, этап 1): доступ, шифрование особых полей,
представители, заметки, журнал просмотров."""
from app.core import field_crypto
from app.core.config import get_settings
from app.models import AuditLog, Student, StudentProfile

SPECIAL = {"is_orphan": True, "disability_group": "3", "health_note": "аллергия на пыльцу", "pdn_kdn": True}


def _student(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).first()


def _foreign_student(db, group):
    return db.query(Student).filter(Student.study_group_id != group.id).first()


def test_curator_reads_and_updates_own_student_dossier(client, curator_headers, curator_group, db):
    s = _student(db, curator_group)
    r = client.put(
        f"/students/{s.id}/dossier/profile", headers=curator_headers,
        json={"phone": " +7 900 000-00-00 ", "funding": "budget"},
    )
    assert r.status_code == 200
    assert r.json()["profile"]["phone"] == "+7 900 000-00-00"
    assert r.json()["profile"]["funding"] == "budget"
    r = client.get(f"/students/{s.id}/dossier", headers=curator_headers)
    assert r.json()["profile"]["phone"] == "+7 900 000-00-00"


def test_curator_cannot_open_foreign_student_dossier(client, curator_headers, curator_group, db):
    s = _foreign_student(db, curator_group)
    assert client.get(f"/students/{s.id}/dossier", headers=curator_headers).status_code == 403
    assert client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={}).status_code == 403
    assert client.post(
        f"/students/{s.id}/dossier/notes", headers=curator_headers, json={"text": "x"}
    ).status_code == 403


def test_special_fields_are_encrypted_at_rest(client, curator_headers, curator_group, db):
    s = _student(db, curator_group)
    r = client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"special": SPECIAL})
    assert r.status_code == 200
    assert r.json()["special"]["is_orphan"] is True

    db.expire_all()
    raw = db.get(StudentProfile, s.id).special_enc
    assert raw and "аллергия" not in raw and "orphan" not in raw
    assert field_crypto.decrypt_json(raw)["health_note"] == "аллергия на пыльцу"

    r = client.get(f"/students/{s.id}/dossier", headers=curator_headers)
    assert r.json()["special"]["disability_group"] == "3"


def test_profile_update_without_special_keeps_special(client, curator_headers, curator_group, db):
    s = _student(db, curator_group)
    client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"special": SPECIAL})
    r = client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"phone": "123"})
    assert r.json()["special"]["pdn_kdn"] is True


def test_audit_log_never_contains_values(client, curator_headers, curator_group, db):
    s = _student(db, curator_group)
    client.put(
        f"/students/{s.id}/dossier/profile", headers=curator_headers,
        json={"phone": "+79001112233", "special": SPECIAL},
    )
    entries = db.query(AuditLog).filter(AuditLog.action == "dossier.profile_update").all()
    assert entries and entries[0].new_value == "phone,special"
    assert all("79001112233" not in (e.new_value or "") for e in entries)


def test_special_fields_unavailable_without_key(client, curator_headers, curator_group, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "dossier_encryption_key", "")
    s = _student(db, curator_group)
    r = client.get(f"/students/{s.id}/dossier", headers=curator_headers)
    assert r.status_code == 200
    assert r.json()["special"] is None and r.json()["special_available"] is False
    r = client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"special": SPECIAL})
    assert r.status_code == 503
    # без особых полей профиль по-прежнему сохраняется
    r = client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"phone": "1"})
    assert r.status_code == 200


def test_guardians_crud_and_single_primary(client, curator_headers, curator_group, db):
    s = _student(db, curator_group)
    base = f"/students/{s.id}/dossier/guardians"
    a = client.post(base, headers=curator_headers, json={"full_name": "Иванова А.", "relation": "мать", "is_primary": True})
    b = client.post(base, headers=curator_headers, json={"full_name": "Иванов Б.", "relation": "отец", "is_primary": True})
    assert a.status_code == b.status_code == 201
    guardians = client.get(f"/students/{s.id}/dossier", headers=curator_headers).json()["guardians"]
    assert [g["is_primary"] for g in guardians] == [True, False]
    assert guardians[0]["full_name"] == "Иванов Б."

    r = client.put(f"{base}/{a.json()['id']}", headers=curator_headers,
                   json={"full_name": "Иванова А.", "relation": "мать", "phone": "555"})
    assert r.status_code == 200 and r.json()["phone"] == "555"
    assert client.delete(f"{base}/{b.json()['id']}", headers=curator_headers).status_code == 204
    assert len(client.get(f"/students/{s.id}/dossier", headers=curator_headers).json()["guardians"]) == 1


def test_guardian_of_other_student_is_not_reachable(client, curator_headers, curator_group, admin_headers, db):
    own, foreign = _student(db, curator_group), _foreign_student(db, curator_group)
    g = client.post(
        f"/students/{foreign.id}/dossier/guardians", headers=admin_headers,
        json={"full_name": "Чужой П.", "relation": "отец"},
    ).json()
    # id чужого представителя через «свой» студент не найти
    r = client.delete(f"/students/{own.id}/dossier/guardians/{g['id']}", headers=curator_headers)
    assert r.status_code == 404


def test_notes_only_author_or_admin_can_delete(client, curator_headers, curator_group, admin_headers, db):
    s = _student(db, curator_group)
    note = client.post(
        f"/students/{s.id}/dossier/notes", headers=curator_headers, json={"kind": "call", "text": "Звонок маме"}
    ).json()
    assert note["can_delete"] is True

    # админ видит и может удалить чужую
    listed = client.get(f"/students/{s.id}/dossier", headers=admin_headers).json()["notes"]
    assert listed[0]["text"] == "Звонок маме" and listed[0]["can_delete"] is True

    own = client.post(f"/students/{s.id}/dossier/notes", headers=admin_headers, json={"text": "Заметка админа"}).json()
    # куратор чужую удалить не может
    assert client.delete(f"/students/{s.id}/dossier/notes/{own['id']}", headers=curator_headers).status_code == 403
    assert client.delete(f"/students/{s.id}/dossier/notes/{note['id']}", headers=admin_headers).status_code == 204


def test_access_log_records_views_and_is_admin_only(client, curator_headers, curator_group, admin_headers, db):
    s = _student(db, curator_group)
    client.get(f"/students/{s.id}/dossier", headers=curator_headers)
    assert client.get(f"/students/{s.id}/dossier/access-log", headers=curator_headers).status_code == 403
    rows = client.get(f"/students/{s.id}/dossier/access-log", headers=admin_headers).json()
    assert len(rows) == 1 and rows[0]["included_special"] is True


def test_dept_head_and_edu_department_access(client, dept_head_headers, edu_department_headers, curator_group, db):
    s = _student(db, curator_group)
    for headers in (dept_head_headers, edu_department_headers):
        assert client.get(f"/students/{s.id}/dossier", headers=headers).status_code == 200


# ---------- удаление и обезличивание: досье не должно переживать студента ----------

def _fill_everything(client, headers, student):
    client.put(f"/students/{student.id}/dossier/profile", headers=headers,
               json={"phone": "+7 900 000-00-00", "special": SPECIAL})
    client.post(f"/students/{student.id}/dossier/guardians", headers=headers, json={"full_name": "Мать", "relation": "мать"})
    client.post(f"/students/{student.id}/dossier/notes", headers=headers, json={"text": "Беседа"})
    client.get(f"/students/{student.id}/dossier", headers=headers)  # запись в журнале просмотров


def _dossier_rows(db, student_id):
    from app.models import DossierAccessLog, StudentGuardian, StudentNote

    db.expire_all()
    return (
        db.query(StudentProfile).filter(StudentProfile.student_id == student_id).count(),
        db.query(StudentGuardian).filter(StudentGuardian.student_id == student_id).count(),
        db.query(StudentNote).filter(StudentNote.student_id == student_id).count(),
        db.query(DossierAccessLog).filter(DossierAccessLog.student_id == student_id).count(),
    )


def test_deleting_a_student_erases_the_dossier(client, curator_headers, admin_headers, curator_group, db):
    from app.models import StudentStatus

    s = _student(db, curator_group)
    sid = s.id
    _fill_everything(client, curator_headers, s)
    assert _dossier_rows(db, sid) == (1, 1, 1, 2)  # в журнале: сохранение и просмотр
    client.patch(f"/admin/students/{sid}/status", headers=admin_headers, json={"status": "expelled", "left_at": "2026-09-10"})
    r = client.delete(f"/admin/students/{sid}", headers=admin_headers)
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert _dossier_rows(db, sid) == (0, 0, 0, 0)
    assert db.get(Student, sid) is None


def test_anonymizing_a_student_with_history_also_erases_the_dossier(client, curator_headers, admin_headers, curator_group, db, today):
    """Есть отметки посещаемости → студента обезличивают, а не удаляют; досье при этом обязано исчезнуть."""
    from app.services.attendance_service import get_active_students

    import datetime

    day = today
    while day.weekday() >= 5:  # отметки ставят только в учебные дни — берём ближайший будний
        day -= datetime.timedelta(days=1)
    s = get_active_students(db, curator_group.id, day)[0]
    sid = s.id
    r = client.post(f"/curator/groups/{curator_group.id}/day/submit?date={day}", headers=curator_headers,
                    json={"exceptions": [{"student_id": sid, "mark_code": "б"}]})
    assert r.status_code == 200, r.text
    _fill_everything(client, curator_headers, s)
    client.patch(f"/admin/students/{sid}/status", headers=admin_headers, json={"status": "expelled", "left_at": "2026-09-10"})
    r = client.delete(f"/admin/students/{sid}", headers=admin_headers)
    assert r.status_code == 200 and r.json()["anonymized"] is True
    profile, guardians, notes, log = _dossier_rows(db, sid)
    assert (profile, guardians, notes) == (0, 0, 0)
    assert log == 2  # след доступа (id и кто смотрел, без ПДн) остаётся
    assert db.get(Student, sid).last_name == "Удалённый"


def test_force_deleting_a_group_erases_students_dossiers_and_task_assignments(client, curator_headers, admin_headers, curator_group, db):
    from app.models import TaskAssignment

    s = _student(db, curator_group)
    sid, group_id, group_code = s.id, curator_group.id, curator_group.code
    _fill_everything(client, curator_headers, s)
    task = client.post("/tasks", headers=admin_headers, json={
        "title": "Т", "collect_mode": "student", "reviewer_rule": "none",
        "due_date": str(__import__("datetime").date.today() + __import__("datetime").timedelta(days=5)),
        "fields": [{"label": "Заметка", "type": "text"}], "scope": {"group_ids": [group_id]},
    }).json()
    aid = task["assignments"][0]["id"]
    client.put(f"/tasks/assignments/{aid}/answers", headers=curator_headers,
               json={"rows": [{"student_id": s.id, "values": {task["fields"][0]["key"]: "текст"}}]})
    client.patch(f"/admin/groups/{group_id}", headers=admin_headers, json={"is_active": False})
    r = client.delete(f"/admin/groups/{group_id}?force=true&confirm_code={group_code}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert _dossier_rows(db, sid) == (0, 0, 0, 0)
    assert db.query(TaskAssignment).filter(TaskAssignment.study_group_id == group_id).count() == 0


def test_saving_the_dossier_is_logged_as_a_view_of_special_fields(client, curator_headers, admin_headers, curator_group, db):
    s = _student(db, curator_group)
    client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"phone": "1"})
    rows = client.get(f"/students/{s.id}/dossier/access-log", headers=admin_headers).json()
    assert len(rows) == 1 and rows[0]["included_special"] is True
