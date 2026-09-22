"""М3: приказ/справка — необязательное дополнение к коду отметки, без
контроля дедлайна и без отдельного экрана «на подтверждение» (обновление 1.1).
"""


def test_document_code_without_reference_is_not_blocked(client, curator_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students
    from app.models import AttendanceMark, BasisStatus

    student = get_active_students(db, curator_group.id, today)[0]
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date={today}",
        headers=curator_headers,
        json={"exceptions": [{"student_id": student.id, "mark_code": "б", "comment": None, "basis_reference": None}]},
    )
    assert r.status_code == 200, r.text

    mark = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == student.id, AttendanceMark.date == today
    ).one()
    assert mark.basis_status == BasisStatus.NOT_REQUIRED
    assert mark.basis_deadline is None


def test_document_code_with_reference_is_confirmed(client, curator_headers, curator_group, db, today):
    from app.services.attendance_service import get_active_students
    from app.models import AttendanceMark, BasisStatus

    student = get_active_students(db, curator_group.id, today)[0]
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date={today}",
        headers=curator_headers,
        json={
            "exceptions": [
                {"student_id": student.id, "mark_code": "б", "comment": None, "basis_reference": "Справка №5"}
            ]
        },
    )
    assert r.status_code == 200, r.text

    mark = db.query(AttendanceMark).filter(
        AttendanceMark.student_id == student.id, AttendanceMark.date == today
    ).one()
    assert mark.basis_status == BasisStatus.CONFIRMED
    assert mark.basis_reference == "Справка №5"


def test_pending_basis_dashboard_removed(client, admin_headers):
    r = client.get("/dashboards/pending-basis", headers=admin_headers)
    assert r.status_code == 404
