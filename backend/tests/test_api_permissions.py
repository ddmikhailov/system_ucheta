from app.models import StudyGroup


def test_curator_cannot_access_other_groups_day(client, curator_headers, curator_group, db, today):
    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    r = client.get(f"/curator/groups/{other_group.id}/day?date={today}", headers=curator_headers)
    assert r.status_code == 403


def test_curator_can_access_own_group_day(client, curator_headers, curator_group, today):
    r = client.get(f"/curator/groups/{curator_group.id}/day?date={today}", headers=curator_headers)
    assert r.status_code == 200


def test_curator_cannot_access_dashboards(client, curator_headers, today):
    r = client.get(f"/dashboards/day?date={today}", headers=curator_headers)
    assert r.status_code == 403


def test_curator_cannot_access_admin_endpoints(client, curator_headers):
    r = client.get("/admin/users", headers=curator_headers)
    assert r.status_code == 403


def test_dept_head_can_access_dashboards(client, dept_head_headers, today):
    r = client.get(f"/dashboards/day?date={today}", headers=dept_head_headers)
    assert r.status_code == 200


def test_dept_head_cannot_reach_admin_only_creation(client, dept_head_headers):
    r = client.post("/admin/departments", headers=dept_head_headers, json={"name": "Новое отделение"})
    assert r.status_code == 403


def test_dept_head_cannot_edit_mark_codes(client, dept_head_headers, db):
    from app.models import MarkCode

    mark = db.query(MarkCode).filter(MarkCode.code == "о").one()
    r = client.patch(f"/admin/mark-codes/{mark.id}", headers=dept_head_headers, json={"is_active": False})
    assert r.status_code == 403


def test_edu_department_can_edit_mark_codes(client, edu_department_headers, db):
    from app.models import MarkCode

    mark = db.query(MarkCode).filter(MarkCode.code == "о").one()
    r = client.patch(f"/admin/mark-codes/{mark.id}", headers=edu_department_headers, json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_edu_department_cannot_create_users(client, edu_department_headers):
    r = client.post(
        "/admin/users",
        headers=edu_department_headers,
        json={"full_name": "Тест Тестов", "username": "test.t", "role": "curator"},
    )
    assert r.status_code == 403


def test_unauthenticated_requests_rejected(client, seeded, today):
    assert client.get(f"/dashboards/day?date={today}").status_code == 401
    assert client.get("/curator/groups").status_code == 401
    assert client.get("/admin/users").status_code == 401
