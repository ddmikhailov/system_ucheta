"""Релиз 3.5.0: выключаемые модули — в релизном наборе скрытые разделы недоступны всем ролям."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.modules import ALL_MODULES, HIDDEN_IN_RELEASE, RELEASE_MODULES, parse_modules
from app.db.session import get_db
from app.main import MODULE_ROUTERS, include_module_routers
import app.db.base as db_base


@pytest.fixture()
def release_mode(monkeypatch):
    """Релизный набор: переменная ENABLED_MODULES не задана."""
    monkeypatch.setattr(get_settings(), "enabled_modules", "")


def _paths(router):
    """Все (метод, путь) роутера, включая вложенные (админка собрана из подроутеров) — по схеме OpenAPI."""
    flat = FastAPI()
    flat.include_router(router)
    for path, operations in flat.openapi()["paths"].items():
        for method in operations:
            yield method.upper(), _fill(path)


def _fill(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "1", path)


def _fresh_client(test_engine, modules):
    application = FastAPI()
    include_module_routers(application, modules)

    def override_get_db():
        session = db_base.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    return TestClient(application)


def test_hidden_routers_answer_404_for_every_route_in_release_set(test_engine):
    client = _fresh_client(test_engine, parse_modules(""))
    checked = 0
    for router, module in MODULE_ROUTERS:
        if module is None or module in RELEASE_MODULES:
            continue
        assert module in HIDDEN_IN_RELEASE
        for method, path in _paths(router):
            r = client.request(method, path)
            assert r.status_code == 404, f"{method} {path} должен быть недоступен (модуль {module})"
            checked += 1
    assert checked >= 36  # досье, паспорт, индивидуальная работа, план, собрания, отчёты, импорт досье


def test_release_routers_stay_connected(test_engine):
    client = _fresh_client(test_engine, parse_modules(""))
    for router, module in MODULE_ROUTERS:
        if module is not None and module not in RELEASE_MODULES:
            continue
        for method, path in _paths(router):
            assert client.request(method, path).status_code != 404, f"{method} {path} пропал из релизного набора"


def test_all_modules_mode_connects_every_router(test_engine):
    client = _fresh_client(test_engine, parse_modules("all"))
    for router, _module in MODULE_ROUTERS:
        for method, path in _paths(router):
            assert client.request(method, path).status_code != 404, f"{method} {path}"


def test_me_lists_enabled_modules(client, admin_headers, release_mode):
    r = client.get("/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["modules"] == sorted(RELEASE_MODULES)


def test_me_lists_every_module_in_all_mode(client, admin_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "enabled_modules", "all")
    assert client.get("/auth/me", headers=admin_headers).json()["modules"] == sorted(ALL_MODULES)


def test_change_password_response_carries_modules(client, db, curator_user, curator_headers, release_mode):
    r = client.post("/auth/change-password", headers=curator_headers,
                    json={"current_password": "CuratorTest123!", "new_password": "NewCurator456#Pass"})
    assert r.status_code == 200, r.text
    assert r.json()["modules"] == sorted(RELEASE_MODULES)


def test_word_documents_from_dossier_are_hidden_in_release(client, admin_headers, curator_headers, curator_group, release_mode):
    for headers in (admin_headers, curator_headers):
        for suffix in ("roster-sheet", "cards"):
            r = client.get(f"/curator/groups/{curator_group.id}/{suffix}?fields=full_name", headers=headers)
            assert r.status_code == 404, f"{suffix}: {r.status_code}"


def test_word_documents_work_when_dossier_enabled(client, curator_headers, curator_group, monkeypatch):
    monkeypatch.setattr(get_settings(), "enabled_modules", "all")
    for suffix in ("roster-sheet", "cards"):
        r = client.get(f"/curator/groups/{curator_group.id}/{suffix}?fields=full_name", headers=curator_headers)
        assert r.status_code == 200, f"{suffix}: {r.status_code} {r.text[:200]}"


# ---------- сквозные связи: задачи и «Мой день» ----------

import datetime

from app.core.time import today_local
from app.models import Student, StudentProfile
from app.services import my_day_service
from tests.test_task_dossier import PHONE, _assignment_id, _create, _fill_and_submit, _students


def test_dossier_fields_for_tasks_are_empty_in_release(client, admin_headers, release_mode):
    r = client.get("/tasks/dossier-fields", headers=admin_headers)
    assert r.status_code == 200 and r.json() == []


def test_task_cannot_link_a_field_to_the_dossier_in_release(client, admin_headers, imported, release_mode):
    r = _create(client, admin_headers, [PHONE])
    assert r.status_code == 400
    assert "Привязка к досье недоступна" in r.json()["detail"]
    plain = _create(client, admin_headers, [{"label": "Телефон", "type": "text"}])
    assert plain.status_code == 201, plain.text


def test_old_linked_task_is_accepted_but_dossier_stays_untouched(
    client, admin_headers, dept_head_headers, curator_headers, curator_group, imported, db, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "enabled_modules", "all")
    task = _create(client, admin_headers, [PHONE]).json()
    aid = _assignment_id(client, curator_headers, task["id"])
    students = _students(db, curator_group)
    monkeypatch.setattr(get_settings(), "enabled_modules", "")  # релиз
    form = client.get(f"/tasks/assignments/{aid}", headers=curator_headers)
    assert form.status_code == 200 and not any(r.get("from_dossier") for r in form.json()["rows"])
    key = task["fields"][0]["key"]
    assert _fill_and_submit(client, curator_headers, aid, students, {0: {key: "+7 900 000-00-01"}}).status_code == 200
    r = client.post(f"/tasks/assignments/{aid}/review", headers=dept_head_headers, json={"action": "accept"})
    assert r.status_code == 200, r.text
    db.expire_all()
    profile = db.get(StudentProfile, students[0].id)
    assert profile is None or profile.phone is None


def test_my_day_has_no_individual_work_and_no_birthdays_in_release(
    client, curator_headers, curator_user, curator_group, imported, db, monkeypatch,
):
    today = today_local()
    student = db.query(Student).filter(Student.study_group_id == curator_group.id).order_by(Student.id).first()
    db.add(StudentProfile(student_id=student.id, birth_date=datetime.date(today.year - 17, today.month, today.day)))
    db.commit()
    monkeypatch.setattr(get_settings(), "enabled_modules", "all")
    full = my_day_service.build_my_day(db, curator_user, today)
    assert [b.student_id for b in full.birthdays] == [student.id]
    monkeypatch.setattr(get_settings(), "enabled_modules", "")
    db.expire_all()
    day = my_day_service.build_my_day(db, curator_user, today)
    assert day.attention == [] and day.attention_total == 0 and day.birthdays == []
    assert day.leads_groups and day.groups
    assert client.get("/my-day", headers=curator_headers).status_code == 200


def test_followup_reminders_are_not_created_in_release(db, curator_user, monkeypatch):
    from app.services import task_service

    called = []
    monkeypatch.setattr(task_service.individual_work_service, "generate_followup_reminders",
                        lambda *a, **k: called.append(1) or 0)
    monkeypatch.setattr(get_settings(), "enabled_modules", "")
    task_service.generate_reminders(db, curator_user, today_local(), force=True)
    assert called == []


def test_release_features_work_end_to_end(client, curator_headers, curator_user, curator_group, imported, db, today, release_mode):
    """Всё, что остаётся в релизе, отвечает под куратором при выключенных остальных модулях."""
    gid = curator_group.id
    student = db.query(Student).filter(Student.study_group_id == gid).order_by(Student.id).first()
    for path in (
        f"/curator/groups/{gid}/day?date={today}",   # посещаемость
        "/curator/groups",
        "/my-day",
        "/my-day/counters",
        f"/students/{student.id}",                    # карточка (без досье)
        f"/students/{student.id}/attendance?year={today.year}&month={today.month}",
        "/tasks/my",
        f"/my-id/groups/{gid}",
        f"/meals/groups/{gid}",
        "/notifications",
    ):
        r = client.get(path, headers=curator_headers)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
    assert "dossier" not in client.get(f"/students/{student.id}", headers=curator_headers).text
