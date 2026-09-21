def _submit_hospital_leave(client, curator_headers, group_id, student_id, date):
    r = client.post(
        f"/curator/groups/{group_id}/day/submit?date={date}",
        headers=curator_headers,
        json={"exceptions": [{"student_id": student_id, "mark_code": "б", "comment": None, "basis_reference": None}]},
    )
    assert r.status_code == 200, r.text


def test_pending_basis_appears_after_submission(client, curator_headers, curator_group, admin_headers, db, today):
    from app.services.attendance_service import get_active_students

    student = get_active_students(db, curator_group.id, today)[0]
    _submit_hospital_leave(client, curator_headers, curator_group.id, student.id, today)

    r = client.get("/dashboards/pending-basis", headers=admin_headers)
    assert r.status_code == 200
    rows = r.json()
    target = next(row for row in rows if row["student_id"] == student.id)
    assert target["is_overdue"] is False
    assert target["mark_code"] == "б"


def test_dept_head_sees_and_confirms_basis_in_own_department(
    client, curator_headers, curator_group, dept_head_headers, db, today
):
    from app.services.attendance_service import get_active_students

    student = get_active_students(db, curator_group.id, today)[0]
    _submit_hospital_leave(client, curator_headers, curator_group.id, student.id, today)

    r = client.get("/dashboards/pending-basis", headers=dept_head_headers)
    mark_id = next(row["mark_id"] for row in r.json() if row["student_id"] == student.id)

    r = client.patch(
        f"/dashboards/pending-basis/{mark_id}", headers=dept_head_headers,
        json={"basis_reference": "Справка №5 от 21.09.2026"},
    )
    assert r.status_code == 200
    assert r.json()["basis_status"] == "confirmed"

    r = client.get("/dashboards/pending-basis", headers=dept_head_headers)
    assert not any(row["mark_id"] == mark_id for row in r.json())


def test_curator_cannot_confirm_basis(client, curator_headers, curator_group, admin_headers, db, today):
    from app.services.attendance_service import get_active_students

    student = get_active_students(db, curator_group.id, today)[0]
    _submit_hospital_leave(client, curator_headers, curator_group.id, student.id, today)

    r = client.get("/dashboards/pending-basis", headers=admin_headers)
    mark_id = next(row["mark_id"] for row in r.json() if row["student_id"] == student.id)

    r = client.patch(
        f"/dashboards/pending-basis/{mark_id}", headers=curator_headers,
        json={"basis_reference": "Справка"},
    )
    assert r.status_code == 403


def test_empty_basis_reference_rejected(client, admin_headers, curator_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students

    student = get_active_students(db, curator_group.id, today)[0]
    _submit_hospital_leave(client, curator_headers, curator_group.id, student.id, today)

    r = client.get("/dashboards/pending-basis", headers=admin_headers)
    mark_id = next(row["mark_id"] for row in r.json() if row["student_id"] == student.id)

    r = client.patch(f"/dashboards/pending-basis/{mark_id}", headers=admin_headers, json={"basis_reference": ""})
    assert r.status_code == 422


def test_confirm_nonexistent_mark_returns_404(client, admin_headers):
    r = client.patch("/dashboards/pending-basis/999999", headers=admin_headers, json={"basis_reference": "x"})
    assert r.status_code == 404
