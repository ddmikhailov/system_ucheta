"""Граница роли «Ответственная по питанию»: кроме вкладки «Питание» ей не открыт ни один раздел.

Проверка идёт по ВСЕМ GET-маршрутам из схемы приложения, а не по списку «известных» — иначе новый эндпоинт с
запрещающей (а не разрешающей) проверкой роли молча отдал бы ей данные. Так уже случилось с поиском студентов
(`GET /students`: раньше он закрывался только для кураторов)."""
import re

import pytest

from app.main import app

# Что роль вправе читать: свои данные, справочники, пустые для неё списки и само питание.
ALLOWED_PREFIXES = ("/meals", "/health")
ALLOWED_EXACT = {
    "/auth/me", "/curator/settings", "/curator/mark-codes", "/notifications", "/notifications/unread-count",
}
# Эти списки строятся по назначениям на группы; у ответственной по питанию их нет, ответ обязан быть пустым.
MUST_BE_EMPTY = ("/curator/groups", "/individual-work/groups", "/tasks/my", "/tasks")

PARAMS = {
    "date": "2026-10-08", "date_from": "2026-10-01", "date_to": "2026-10-08", "as_of_date": "2026-10-08",
    "year": "2026", "month": "10", "fields": "full_name", "semester": "1", "q": "а",
}


def _fill(path, group_id, student_id):
    url = re.sub(r"\{study_group_id\}|\{group_id\}", str(group_id), path)
    url = re.sub(r"\{student_id\}", str(student_id), url)
    return re.sub(r"\{[^}]+\}", "1", url)


def test_meal_manager_reads_nothing_but_meals(client, meal_manager_headers, imported, curator_group, db):
    from app.models import Student

    student = db.query(Student).filter(Student.study_group_id == curator_group.id).first()
    spec = app.openapi()["paths"]
    leaks = []
    for path, ops in spec.items():
        if "get" not in ops or path.startswith(ALLOWED_PREFIXES) or path in ALLOWED_EXACT:
            continue
        params = {
            p["name"]: PARAMS.get(p["name"], "1")
            for p in ops["get"].get("parameters", []) if p["in"] == "query" and p.get("required")
        }
        r = client.get(_fill(path, curator_group.id, student.id), params=params, headers=meal_manager_headers)
        if r.status_code in (403, 404):  # 404 — объекта с таким номером нет, данных не отдано
            continue
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        if path in MUST_BE_EMPTY and r.status_code == 200 and body in ([], {}):
            continue
        if path in ("/my-day", "/my-day/counters", "/passport/summary", "/passport/export") and r.status_code == 200:
            # пустые для роли без групп: ни групп, ни задач, ни строк
            if path == "/my-day":
                assert body["groups"] == [] and body["tasks"] == []
            elif path == "/my-day/counters":
                assert not any(body.values())
            elif path == "/passport/summary":
                assert body.get("rows", body.get("groups", [])) in ([], None) or not body.get("rows")
            continue
        leaks.append((path, r.status_code, (r.text or "")[:80]))
    assert not leaks, f"ответственной по питанию открыто лишнее: {leaks}"


def test_meal_manager_cannot_write_anything_outside_meals(client, meal_manager_headers, imported, curator_group):
    spec = app.openapi()["paths"]
    for path, ops in spec.items():
        if path.startswith(ALLOWED_PREFIXES) or path in (
            "/auth/logout", "/auth/login", "/auth/change-password", "/notifications/read-all",  # свои уведомления
        ):
            continue
        for method in ("post", "put", "patch", "delete"):
            if method not in ops:
                continue
            r = client.request(method.upper(), _fill(path, curator_group.id, 1), json={}, headers=meal_manager_headers)
            # 403 — закрыто; 404/422 — объекта нет или тело не прошло проверку, а значит изменения не было.
            assert r.status_code in (403, 404, 405, 422), (method, path, r.status_code)
