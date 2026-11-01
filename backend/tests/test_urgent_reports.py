"""Срочное сообщение заведующему (п. 3.1.26 положения): отправка куратором, колокольчик, чтение и приём."""
import pytest


@pytest.fixture()
def student_id(curator_group, db, today):
    from app.services.attendance_service import get_active_students

    return get_active_students(db, curator_group.id, today)[0].id


def _send(client, headers, student_id, text="Драка в общежитии, вызвана охрана"):
    return client.post("/urgent-reports", headers=headers, json={"student_id": student_id, "category": "emergency", "text": text})


def test_curator_sends_and_dept_head_gets_bell_without_text(client, curator_headers, dept_head_headers, dept_head_user, student_id, db):
    from app.models import InAppNotification, UrgentReport

    r = _send(client, curator_headers, student_id)
    assert r.status_code == 201, r.text
    assert r.json()["text"] is None  # автору текст не возвращается
    assert "Драка" not in db.query(UrgentReport).one().text_enc  # в БД текст зашифрован

    bell = db.query(InAppNotification).filter(InAppNotification.user_id == dept_head_user.id, InAppNotification.kind == "urgent_report").one()
    assert "Драка" not in bell.message
    assert bell.category == "manage"
    assert bell.entity_id == str(r.json()["id"])


def test_reader_sees_text_and_acknowledges_author_is_notified(client, curator_headers, curator_user, dept_head_headers, student_id, db):
    from app.models import AuditLog, InAppNotification

    report_id = _send(client, curator_headers, student_id).json()["id"]
    inbox = client.get("/urgent-reports?only_open=true", headers=dept_head_headers).json()
    assert [x["id"] for x in inbox] == [report_id]
    assert inbox[0]["text"] == "Драка в общежитии, вызвана охрана"

    r = client.post(f"/urgent-reports/{report_id}/acknowledge", headers=dept_head_headers)
    assert r.status_code == 200 and r.json()["acknowledged_by_name"]
    assert client.get("/urgent-reports?only_open=true", headers=dept_head_headers).json() == []

    mine = client.get(f"/urgent-reports/for-student/{student_id}", headers=curator_headers).json()
    assert mine[0]["acknowledged_by_name"] and mine[0]["text"] is None
    assert db.query(InAppNotification).filter(InAppNotification.user_id == curator_user.id, InAppNotification.kind == "urgent_report_ack").count() == 1
    actions = {a.action for a in db.query(AuditLog).all()}
    assert {"urgent_report.create", "urgent_report.view", "urgent_report.acknowledge"} <= actions


def test_edu_department_is_notified_and_reads(client, curator_headers, edu_department_headers, edu_department_user, student_id, db):
    from app.models import InAppNotification

    report_id = _send(client, curator_headers, student_id).json()["id"]
    assert db.query(InAppNotification).filter(InAppNotification.user_id == edu_department_user.id, InAppNotification.kind == "urgent_report").count() == 1
    assert client.get("/urgent-reports", headers=edu_department_headers).json()[0]["id"] == report_id


def test_admin_notified_only_without_dept_head(client, curator_headers, admin_headers, student_id, db):
    from app.models import InAppNotification, User

    admin_user = db.query(User).filter(User.username == "admin").one()

    _send(client, curator_headers, student_id)
    assert db.query(InAppNotification).filter(InAppNotification.user_id == admin_user.id, InAppNotification.kind == "urgent_report").count() == 1
    assert len(client.get("/urgent-reports", headers=admin_headers).json()) == 1


def test_curator_cannot_read_or_acknowledge(client, curator_headers, student_id):
    report_id = _send(client, curator_headers, student_id).json()["id"]
    assert client.get("/urgent-reports", headers=curator_headers).status_code == 403
    assert client.post(f"/urgent-reports/{report_id}/acknowledge", headers=curator_headers).status_code == 403


def test_foreign_curator_cannot_send_for_other_group_student(client, db_second_curator, student_id):
    from tests.conftest import _login

    headers = _login(client, db_second_curator.username, "SecondCura#58x!")
    assert _send(client, headers, student_id).status_code == 403


def test_text_is_validated(client, curator_headers, student_id):
    assert _send(client, curator_headers, student_id, text="а").status_code == 422
    r = client.post("/urgent-reports", headers=curator_headers, json={"student_id": student_id, "category": "joke", "text": "Текст сообщения"})
    assert r.status_code == 422


def test_reports_erased_with_student(client, curator_headers, admin_headers, student_id, db):
    from app.models import UrgentReport

    _send(client, curator_headers, student_id)
    client.patch(f"/admin/students/{student_id}", headers=admin_headers, json={"status": "expelled"})
    assert client.delete(f"/admin/students/{student_id}?force=true", headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.query(UrgentReport).count() == 0


def test_reconciliation_note_kind_is_accepted(client, curator_headers, student_id):
    r = client.post(f"/students/{student_id}/dossier/notes", headers=curator_headers, json={"kind": "reconciliation", "text": "Встреча сторон"})
    assert r.status_code in (200, 201), r.text


def test_pd_changes_list_for_admin_only(client, admin_headers, curator_headers, dept_head_headers, student_id):
    r = client.patch(f"/admin/students/{student_id}", headers=admin_headers, json={"last_name": "Новофамильев"})
    assert r.status_code == 200, r.text
    client.patch(f"/admin/students/{student_id}", headers=admin_headers, json={"status": "studying"})  # не ПДн
    client.put(f"/students/{student_id}/dossier/profile", headers=curator_headers, json={"phone": "+70000000000"})

    rows = client.get("/admin/pd-changes", headers=admin_headers).json()
    changes = sorted(c for row in rows for c in row["changes"])
    assert changes == ["телефон", "фамилия"]
    assert "Новофамильев" in rows[0]["student_name"] + rows[1]["student_name"]
    assert client.get("/admin/pd-changes", headers=curator_headers).status_code == 403
    assert client.get("/admin/pd-changes", headers=dept_head_headers).status_code == 403
