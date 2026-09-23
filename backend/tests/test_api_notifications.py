"""М6: внутриплатформенные уведомления — единственный канал сейчас,
раз Telegram скрыт из интерфейса."""
import datetime


def _trigger_late_edit(client, curator_headers, group_id, today):
    r = client.post(
        f"/curator/groups/{group_id}/day/submit?date=2026-09-01",
        headers=curator_headers,
        json={"exceptions": []},
    )
    assert r.status_code == 200, r.text


def test_dept_head_receives_and_reads_late_edit_notification(client, curator_headers, curator_group, dept_head_headers):
    # День занятия — 2026-09-01 (см. README про импорт), редактируем его
    # напрямую через API много дней спустя, чтобы наверняка попасть за порог.
    r = client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date=2026-09-01",
        headers=curator_headers,
        json={"exceptions": []},
    )
    assert r.status_code == 200, r.text

    r = client.get("/notifications", headers=dept_head_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    notif = rows[0]
    assert notif["kind"] == "late_edit"
    assert notif["read_at"] is None

    r = client.get("/notifications/unread-count", headers=dept_head_headers)
    assert r.json()["unread"] >= 1

    r = client.post(f"/notifications/{notif['id']}/read", headers=dept_head_headers)
    assert r.status_code == 200
    assert r.json()["read_at"] is not None


def test_curator_does_not_see_dept_heads_notifications(client, curator_headers, curator_group):
    client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date=2026-09-01",
        headers=curator_headers,
        json={"exceptions": []},
    )
    r = client.get("/notifications", headers=curator_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_mark_all_read(client, curator_headers, curator_group, dept_head_headers, db):
    from app.models import Role, User, StudyGroup

    # Ещё одна группа того же отделения — второе уведомление тому же зав. отделением.
    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    curator_role = db.query(Role).filter(Role.code == "curator").one()
    other_curator = db.query(User).filter(User.role_id == curator_role.id, User.department_id.isnot(None)).first()

    client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date=2026-09-01",
        headers=curator_headers,
        json={"exceptions": []},
    )

    r = client.get("/notifications/unread-count", headers=dept_head_headers)
    assert r.json()["unread"] >= 1

    r = client.post("/notifications/read-all", headers=dept_head_headers)
    assert r.status_code == 200

    r = client.get("/notifications/unread-count", headers=dept_head_headers)
    assert r.json()["unread"] == 0


def test_cannot_read_someone_elses_notification(client, curator_headers, curator_group, dept_head_headers, admin_headers):
    client.post(
        f"/curator/groups/{curator_group.id}/day/submit?date=2026-09-01",
        headers=curator_headers,
        json={"exceptions": []},
    )
    r = client.get("/notifications", headers=dept_head_headers)
    notif_id = r.json()[0]["id"]

    r = client.post(f"/notifications/{notif_id}/read", headers=admin_headers)
    assert r.status_code == 404
