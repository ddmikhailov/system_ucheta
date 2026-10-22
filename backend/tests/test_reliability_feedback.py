"""Надёжность и обратная связь (релиз 3.6): /health с проверкой базы, «Сообщить о проблеме», ошибки браузера,
«Что нового» один раз, лимит списка уведомлений, индекс журнала действий, смена ключа досье, Sentry без ПДн."""
import datetime
import logging

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Department, InAppNotification, Role, RoleCode, Student, StudentProfile, StudyGroup, User

PASSWORD = "Proverka#58xQ!"


def _user(db, role: RoleCode, username: str, full_name: str = "Тестов Тест Тестович", active: bool = True) -> User:
    role_row = db.query(Role).filter(Role.code == role.value).one()
    user = User(
        username=username, full_name=full_name, role_id=role_row.id,
        password_hash=hash_password(PASSWORD), is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(client, username: str) -> dict:
    r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


REPORT = {
    "text": "Не сохраняется отметка у студента",
    "page": "/cabinet",
    "version": "3.6.0",
    "browser": "Chrome 141 · Android",
    "screen": "375×812",
}


# --- /health ---


def test_health_ok_when_database_answers(client, seeded):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_503_when_database_is_down(client, seeded, caplog):
    from app.db.session import get_db
    from app.main import app

    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, Exception("Can't connect to MySQL server"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    with caplog.at_level(logging.WARNING):
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "error"
    assert "база данных недоступна" in caplog.text.lower()


# --- «Сообщить о проблеме» ---


@pytest.mark.parametrize("role", [
    RoleCode.CURATOR, RoleCode.DEPUTY_CURATOR, RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.TUTOR,
    RoleCode.SOCIAL_PEDAGOGUE, RoleCode.PSYCHOLOGIST, RoleCode.MEAL_MANAGER, RoleCode.ADMIN,
])
def test_any_role_can_report_a_problem_and_every_active_admin_gets_it(client, db, seeded, role):
    reporter = _user(db, role, "reporter", full_name="Сообщающий Пётр Петрович")
    second_admin = _user(db, RoleCode.ADMIN, "admin2")
    _user(db, RoleCode.ADMIN, "admin_old", active=False)
    bystander = _user(db, RoleCode.CURATOR, "bystander")

    r = client.post("/support/problem-report", json=REPORT, headers=_headers(client, "reporter"))
    assert r.status_code == 200, r.text
    seed_admin = db.query(User).filter(User.username == "admin").one()
    active_admins = {seed_admin.id, second_admin.id} | ({reporter.id} if role == RoleCode.ADMIN else set())
    assert r.json() == {"delivered": len(active_admins)}

    rows = db.query(InAppNotification).filter(InAppNotification.kind == "problem_report").all()
    assert {n.user_id for n in rows} == active_admins
    assert bystander.id not in {n.user_id for n in rows}
    message = rows[0].message
    assert "Сообщающий Пётр Петрович" in message and REPORT["text"] in message
    assert "/cabinet" in message and "3.6.0" in message and "Chrome 141" in message and "375×812" in message
    assert (rows[0].entity_type, rows[0].entity_id) == ("user", str(reporter.id))


def test_problem_report_long_text_fits_into_notification(client, db, seeded):
    _user(db, RoleCode.CURATOR, "reporter")
    long = dict(REPORT, text="очень длинное описание " * 40, page="/students/" + "1" * 250)
    r = client.post("/support/problem-report", json=long, headers=_headers(client, "reporter"))
    assert r.status_code == 200, r.text
    message = db.query(InAppNotification).filter(InAppNotification.kind == "problem_report").first().message
    assert len(message) <= 500
    assert "…" in message and "версия 3.6.0" in message


def test_problem_report_validation_auth_and_rate_limit(client, db, seeded):
    assert client.post("/support/problem-report", json=REPORT).status_code == 401
    _user(db, RoleCode.CURATOR, "reporter")
    headers = _headers(client, "reporter")
    assert client.post("/support/problem-report", json=dict(REPORT, text=""), headers=headers).status_code == 422
    assert client.post("/support/problem-report", json=dict(REPORT, text="x" * 1001), headers=headers).status_code == 422
    for _ in range(5):
        assert client.post("/support/problem-report", json=REPORT, headers=headers).status_code == 200
    assert client.post("/support/problem-report", json=REPORT, headers=headers).status_code == 429


# --- ошибки браузера ---


def test_client_error_is_logged_and_needs_login(client, db, seeded, caplog):
    error = {"message": "TypeError: x is undefined", "page": "/my-day", "version": "3.6.0", "browser": "Firefox 140",
             "stack": "at f (index.js:1:2)"}
    assert client.post("/support/client-error", json=error).status_code == 401
    user = _user(db, RoleCode.CURATOR, "reporter")
    with caplog.at_level(logging.WARNING):
        r = client.post("/support/client-error", json=error, headers=_headers(client, "reporter"))
    assert r.status_code == 204
    assert "TypeError: x is undefined" in caplog.text and "/my-day" in caplog.text and f"пользователь {user.id}" in caplog.text


def test_client_error_flood_is_dropped_silently(client, db, seeded, caplog):
    _user(db, RoleCode.CURATOR, "reporter")
    headers = _headers(client, "reporter")
    with caplog.at_level(logging.WARNING):
        for i in range(25):
            assert client.post("/support/client-error", json={"message": f"ошибка {i}"}, headers=headers).status_code == 204
    assert caplog.text.count("Ошибка в интерфейсе") == 20


# --- «Что нового» ---


def test_release_seen_is_stored_on_the_user_and_returned_by_me(client, db, seeded):
    _user(db, RoleCode.CURATOR, "reporter")
    headers = _headers(client, "reporter")
    assert client.get("/auth/me", headers=headers).json()["seen_release"] is None
    assert client.post("/support/release-seen", json={"release": "3.6.0"}, headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).json()["seen_release"] == "3.6.0"
    assert client.post("/support/release-seen", json={"release": ""}, headers=headers).status_code == 422


# --- уведомления и журнал ---


def test_notifications_limit_is_capped(client, db, seeded):
    user = _user(db, RoleCode.CURATOR, "reporter")
    db.add_all(InAppNotification(user_id=user.id, kind="test", message=f"№{i}") for i in range(210))
    db.commit()
    headers = _headers(client, "reporter")
    assert len(client.get("/notifications?limit=100000", headers=headers).json()) == 200
    assert len(client.get("/notifications?limit=0", headers=headers).json()) == 1
    assert len(client.get("/notifications", headers=headers).json()) == 50


def test_month_bounds_follow_college_time_zone():
    from app.services.user_profile_service import month_bounds_utc

    # Москва UTC+3: месяц начинается в 21:00 UTC последнего дня предыдущего; декабрь переходит в январь.
    assert month_bounds_utc("2026-12") == (datetime.datetime(2026, 11, 30, 21), datetime.datetime(2026, 12, 31, 21))


def test_audit_log_has_entity_index(test_engine):
    indexes = {tuple(ix["column_names"]) for ix in inspect(test_engine).get_indexes("audit_log")}
    assert ("entity_type", "entity_id") in indexes


# --- смена ключа шифрования досье ---


def test_multifernet_reads_old_key_and_writes_with_new(monkeypatch):
    from app.core import field_crypto

    settings = get_settings()
    old_key, new_key = settings.dossier_encryption_key, Fernet.generate_key().decode()
    stored = field_crypto.encrypt_json({"health_note": "аллергия"})

    monkeypatch.setattr(settings, "dossier_encryption_key", f"{new_key}, {old_key}")
    assert field_crypto.decrypt_json(stored) == {"health_note": "аллергия"}
    fresh = field_crypto.encrypt_json({"health_note": "новое"})
    rotated = field_crypto.rotate(stored)

    monkeypatch.setattr(settings, "dossier_encryption_key", new_key)
    assert field_crypto.decrypt_json(fresh) == {"health_note": "новое"}
    assert field_crypto.decrypt_json(rotated) == {"health_note": "аллергия"}
    with pytest.raises(field_crypto.EncryptionUnavailable):
        field_crypto.decrypt_json(stored)


def test_bad_key_in_list_makes_encryption_unavailable(monkeypatch):
    from app.core import field_crypto

    settings = get_settings()
    monkeypatch.setattr(settings, "dossier_encryption_key", f"{settings.dossier_encryption_key},не-ключ")
    assert field_crypto.is_available() is False


def test_rotate_script_reencrypts_profiles_without_touching_updated_at(db, seeded, monkeypatch, capsys):
    import scripts.rotate_dossier_key as rotate_script
    from app.core import field_crypto

    group = StudyGroup(code="ТСТ-101", course=1, department_id=db.query(Department).first().id)
    db.add(group)
    db.flush()
    enrolled = datetime.date(2026, 9, 1)
    readable = Student(last_name="Первый", first_name="Студент", study_group_id=group.id, enrolled_at=enrolled)
    lost = Student(last_name="Второй", first_name="Студент", study_group_id=group.id, enrolled_at=enrolled)
    db.add_all([readable, lost])
    db.flush()
    db.add(StudentProfile(student_id=readable.id, special_enc=field_crypto.encrypt_json({"is_orphan": True})))
    db.add(StudentProfile(student_id=lost.id, special_enc=Fernet(Fernet.generate_key()).encrypt(b"{}").decode()))
    db.commit()
    before = db.get(StudentProfile, readable.id).updated_at

    settings = get_settings()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "dossier_encryption_key", f"{new_key},{settings.dossier_encryption_key}")

    assert rotate_script.run(apply=False) == {"перешифровано": 1, "не читается ни одним ключом": 1}
    assert rotate_script.run(apply=True) == {"перешифровано": 1, "не читается ни одним ключом": 1}
    assert "не читается ни одним ключом" in capsys.readouterr().out

    monkeypatch.setattr(settings, "dossier_encryption_key", new_key)
    db.expire_all()
    profile = db.get(StudentProfile, readable.id)
    assert field_crypto.decrypt_json(profile.special_enc) == {"is_orphan": True}
    assert profile.updated_at == before


# --- срок хранения журнала (не больше года) и помесячный архив в админке ---


def test_purge_removes_audit_and_dossier_views_older_than_retention(db, seeded):
    from app.core.time import utcnow
    from app.models import AuditLog, DossierAccessLog
    from app.services import audit_service

    group = StudyGroup(code="ТСТ-102", course=1, department_id=db.query(Department).first().id)
    db.add(group)
    db.flush()
    student = Student(last_name="Третий", first_name="Студент", study_group_id=group.id, enrolled_at=datetime.date(2026, 9, 1))
    db.add(student)
    db.flush()
    viewer = db.query(User).filter(User.username == "admin").one()
    now = utcnow()
    old, fresh = now - datetime.timedelta(days=366), now - datetime.timedelta(days=364)
    for created in (old, fresh):
        db.add(AuditLog(action="mark.create", entity_type="student", entity_id=str(student.id), created_at=created))
        db.add(DossierAccessLog(student_id=student.id, user_id=viewer.id, included_special=False, created_at=created))
    db.commit()

    audit_service.purge_expired_daily(db)
    assert [r.created_at for r in db.query(AuditLog).filter(AuditLog.action == "mark.create")] == [fresh]
    assert [r.created_at for r in db.query(DossierAccessLog)] == [fresh]

    # Раз в сутки: повторный вызов в тот же день ничего не делает.
    db.add(AuditLog(action="mark.create", entity_type="student", entity_id=str(student.id), created_at=old))
    db.commit()
    audit_service.purge_expired_daily(db)
    assert db.query(AuditLog).filter(AuditLog.created_at == old).count() == 1


def test_purge_runs_when_platform_is_opened(client, db, seeded):
    from app.core.time import utcnow
    from app.models import AuditLog

    user = _user(db, RoleCode.CURATOR, "reporter")
    db.add(AuditLog(user_id=user.id, action="mark.create", entity_type="student", entity_id="1",
                    created_at=utcnow() - datetime.timedelta(days=400)))
    db.commit()
    # Периодические задачи (и чистка журнала) запускает проверка при открытии платформы, а не чтение счётчика.
    assert client.post("/notifications/check", headers=_headers(client, "reporter")).status_code == 200
    db.expire_all()
    assert db.query(AuditLog).filter(AuditLog.action == "mark.create").count() == 0


def test_activity_archive_by_month(client, db, seeded, admin_headers):
    from app.core.time import local_to_utc
    from app.models import AuditLog

    user = _user(db, RoleCode.CURATOR, "reporter")
    # 1 октября 01:00 по Москве — это ещё 30 сентября по UTC: месяц считается по местному времени.
    for when in (datetime.datetime(2026, 9, 15, 12), datetime.datetime(2026, 10, 1, 1), datetime.datetime(2026, 10, 20, 9)):
        db.add(AuditLog(user_id=user.id, action="mark.create", entity_type="student", entity_id="1",
                        created_at=local_to_utc(when)))
    db.commit()

    overview = client.get(f"/admin/users/{user.id}/activity/overview", headers=admin_headers)
    assert overview.status_code == 200
    assert [m for m in overview.json()["months"] if m["month"] in ("2026-09", "2026-10")] == [
        {"month": "2026-10", "count": 2}, {"month": "2026-09", "count": 1},
    ]
    october = client.get(f"/admin/users/{user.id}/activity?month=2026-10&area=mark", headers=admin_headers).json()
    assert len(october["items"]) == 2
    september = client.get(f"/admin/users/{user.id}/activity?month=2026-09&area=mark", headers=admin_headers).json()
    assert len(september["items"]) == 1
    assert client.get(f"/admin/users/{user.id}/activity?month=2026-13", headers=admin_headers).status_code == 422
    assert client.get(f"/admin/users/{user.id}/activity/overview", headers=_headers(client, "reporter")).status_code == 403


# --- вкладка «Отладка»: полный журнал действий, только администратор ---


@pytest.mark.parametrize("role", [
    RoleCode.CURATOR, RoleCode.DEPUTY_CURATOR, RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.TUTOR,
    RoleCode.SOCIAL_PEDAGOGUE, RoleCode.PSYCHOLOGIST, RoleCode.MEAL_MANAGER,
])
def test_debug_audit_is_admin_only(client, db, seeded, role):
    _user(db, role, "other")
    assert client.get("/admin/debug/audit", headers=_headers(client, "other")).status_code == 403
    assert client.get("/admin/debug/audit").status_code == 401


def test_debug_audit_shows_who_what_and_values_with_filters(client, db, seeded, admin_headers):
    from app.core.time import local_to_utc
    from app.models import AuditLog

    curator = _user(db, RoleCode.CURATOR, "kurator", full_name="Кураторова Ольга Петровна")
    rows = [
        (curator.id, "mark.update", "student", "15", "н", "б", datetime.datetime(2026, 10, 19, 23, 30)),
        (curator.id, "day.submit", "study_group_day", "3:2026-10-20", None, None, datetime.datetime(2026, 10, 20, 0, 30)),
        (None, "group.archive", "study_group", "3", "active", "скрыта", datetime.datetime(2026, 10, 21, 12, 0)),
    ]
    for user_id, action, entity_type, entity_id, old, new, when in rows:
        db.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                        old_value=old, new_value=new, created_at=local_to_utc(when)))
    db.commit()

    def get(**params):
        r = client.get("/admin/debug/audit", params=params, headers=admin_headers)
        assert r.status_code == 200, r.text
        return r.json()

    mark = get(user_id=curator.id, area="mark")["items"]
    assert len(mark) == 1
    assert mark[0] | {"id": 0, "created_at": ""} == {
        "id": 0, "created_at": "", "user_id": curator.id, "user_name": "Кураторова Ольга Петровна", "user_role": "curator",
        "action": "mark.update", "entity_type": "student", "entity_id": "15", "old_value": "н", "new_value": "б",
        "ip_address": None,
    }
    assert [e["action"] for e in get(entity_type="study_group", entity_id="3")["items"]] == ["group.archive"]
    # Даты — по времени колледжа: 20.10 00:30 по Москве попадает в 20-е, 19.10 23:30 — нет.
    assert [e["action"] for e in get(date_from="2026-10-20", date_to="2026-10-20")["items"]] == ["day.submit"]

    first = get(limit=2, area="mark")
    assert first["next_before_id"] is None
    page1 = get(limit=1, user_id=curator.id)
    page2 = get(limit=1, user_id=curator.id, before_id=page1["next_before_id"])
    assert [page1["items"][0]["action"], page2["items"][0]["action"]] == ["day.submit", "mark.update"]

    # Просмотр пишется в журнал один раз на запрос первой страницы, «ещё» — нет.
    views = db.query(AuditLog).filter(AuditLog.action == "debug.audit_view").count()
    assert views == 5
    assert client.get("/admin/debug/audit?date_from=не-дата", headers=admin_headers).status_code == 422
