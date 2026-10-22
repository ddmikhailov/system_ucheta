"""М6: внутриплатформенные уведомления (колокольчик в шапке) — единственный
канал уведомлений."""
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


def test_reading_purges_notifications_read_long_ago_but_keeps_the_rest(client, db, dept_head_user, dept_head_headers):
    """Ночное задание планировщика, чистившее старое, ушло вместе с ботом —
    теперь прочитанное больше 90 дней назад удаляется при отметке «прочитано»."""
    from app.core.time import utcnow
    from app.models import InAppNotification

    now = utcnow()

    def add(message, created_days_ago, read_days_ago):
        row = InAppNotification(
            user_id=dept_head_user.id, kind="late_edit", message=message,
            created_at=now - datetime.timedelta(days=created_days_ago),
            read_at=None if read_days_ago is None else now - datetime.timedelta(days=read_days_ago),
        )
        db.add(row)
        return row

    add("прочитано давно", 200, 100)
    add("прочитано недавно", 20, 10)
    add("не прочитано, но старое", 300, None)
    fresh = add("новое", 1, None)
    db.commit()

    r = client.post(f"/notifications/{fresh.id}/read", headers=dept_head_headers)
    assert r.status_code == 200, r.text

    db.expire_all()
    left = {n.message for n in db.query(InAppNotification).filter(InAppNotification.user_id == dept_head_user.id)}
    assert left == {"прочитано недавно", "не прочитано, но старое", "новое"}


def test_mark_all_read_also_purges_old_read(client, db, dept_head_user, dept_head_headers):
    from app.core.time import utcnow
    from app.models import InAppNotification

    now = utcnow()
    db.add(InAppNotification(
        user_id=dept_head_user.id, kind="late_edit", message="давно прочитано",
        created_at=now - datetime.timedelta(days=150), read_at=now - datetime.timedelta(days=120),
    ))
    db.add(InAppNotification(user_id=dept_head_user.id, kind="late_edit", message="свежее", created_at=now))
    db.commit()

    assert client.post("/notifications/read-all", headers=dept_head_headers).status_code == 200

    db.expire_all()
    messages = {n.message for n in db.query(InAppNotification).filter(InAppNotification.user_id == dept_head_user.id)}
    assert messages == {"свежее"}


def test_notifications_split_into_work_and_manage_tabs(client, db, dept_head_user, dept_head_headers):
    from app.services import in_app_notification_service as svc

    svc.notify(db, dept_head_user, "task_assigned", "Новая задача по моей группе")
    svc.notify(db, dept_head_user, "late_edit", "Правка дня задним числом")
    svc.notify(db, dept_head_user, "password_reset", "Просят восстановить пароль")
    db.commit()

    work = client.get("/notifications?category=work", headers=dept_head_headers).json()
    manage = client.get("/notifications?category=manage", headers=dept_head_headers).json()
    assert [n["kind"] for n in work] == ["task_assigned"]
    assert {n["kind"] for n in manage} == {"late_edit", "password_reset"}
    assert {n["category"] for n in manage} == {"manage"}
    assert len(client.get("/notifications", headers=dept_head_headers).json()) == 3

    counts = client.get("/notifications/unread-count", headers=dept_head_headers).json()
    assert (counts["unread"], counts["unread_work"], counts["unread_manage"]) == (3, 1, 2)
    # Колокольчик берёт те же числа из общего опроса счётчиков меню и из проверки сроков.
    nav = client.get("/my-day/counters", headers=dept_head_headers).json()
    assert (nav["notifications"], nav["notifications_work"], nav["notifications_manage"]) == (3, 1, 2)
    checked = client.post("/notifications/check", headers=dept_head_headers).json()
    assert (checked["unread_work"], checked["unread_manage"]) == (1, 2)

    # «Прочитать все» во вкладке «Управление» не трогает рабочие.
    assert client.post("/notifications/read-all?category=manage", headers=dept_head_headers).status_code == 200
    counts = client.get("/notifications/unread-count", headers=dept_head_headers).json()
    assert (counts["unread_work"], counts["unread_manage"]) == (1, 0)
