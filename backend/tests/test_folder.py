"""«Папка куратора» (п. 5.1 положения): список из 16 документов, состояние пунктов, выгрузки и права. Данные выдуманные."""
import datetime
import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from app.core.config import get_settings
from app.models import AuditLog, DossierAccessLog, Student
from app.services import folder_service
from tests.test_release_modules import MINIMAL

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CODES = [
    "5.1.1", "5.1.2", "5.1.3", "5.1.4", "5.1.5", "5.1.6", "5.1.7", "5.1.8–5.1.9",
    "5.1.10", "5.1.11", "5.1.12", "5.1.13", "5.1.14", "5.1.15", "5.1.16",
]


def _students(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).order_by(Student.last_name, Student.first_name).all()


def _folder(client, headers, group, **params):
    return client.get(f"/folder/groups/{group.id}", headers=headers, params=params)


def _items(client, headers, group):
    r = _folder(client, headers, group)
    assert r.status_code == 200, r.text
    return {i["code"]: i for i in r.json()["items"]}


def _text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        root = ET.fromstring(archive.read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p"))


def test_folder_lists_every_document_of_clause_5_1(client, curator_headers, curator_group):
    r = _folder(client, curator_headers, curator_group)
    assert r.status_code == 200
    body = r.json()
    assert body["group_code"] == curator_group.code and body["school_year"]
    assert [i["code"] for i in body["items"]] == CODES
    states = {i["code"]: i["state"] for i in body["items"]}
    for code in ("5.1.2", "5.1.16"):
        assert states[code] == "outside"
    assert states["5.1.5"] == "blank"  # справочник преподавателей пуст — ведётся во вкладке «Успеваемость»


def test_every_download_of_the_folder_opens_for_the_curator(client, curator_headers, curator_user, curator_group, db, today):
    student = _students(db, curator_group)[0]
    client.post(f"/events/groups/{curator_group.id}", headers=curator_headers,
                json={"section": "group_org", "title": "Классный час", "event_date": today.isoformat()})
    client.post(f"/meetings/groups/{curator_group.id}", headers=curator_headers, json={"meeting_date": today.isoformat()})
    client.post(f"/students/{student.id}/dossier/notes", headers=curator_headers,
                json={"kind": "conversation", "text": "Обсудили пропуски", "occurred_on": today.isoformat()})
    client.post(f"/assemblies/groups/{curator_group.id}", headers=curator_headers, json={"assembly_date": today.isoformat()})
    r = client.post(f"/instructions/groups/{curator_group.id}", headers=curator_headers,
                    json={"instruction_date": today.isoformat(), "kind": "introductory", "topic": "Правила поведения в колледже"})
    assert r.status_code == 201, r.text
    client.post(f"/groups/{curator_group.id}/subjects", headers=curator_headers, json={"name": "Математика", "teacher_name": "Иванова А. А."})
    items = _items(client, curator_headers, curator_group)
    assert items["5.1.15"]["state"] == "filled" and len(items["5.1.15"]["downloads"]) == 1
    assert items["5.1.5"]["state"] == "filled" and items["5.1.5"]["open_tab"] == "performance"
    assert items["5.1.1"]["state"] == "filled" and items["5.1.7"]["state"] == "filled" and items["5.1.8–5.1.9"]["state"] == "filled"
    assert len(items["5.1.7"]["downloads"]) == 1 and len(items["5.1.8–5.1.9"]["downloads"]) == 1
    assert items["5.1.10"]["state"] == "filled" and items["5.1.10"]["can_add"] == "assembly" and len(items["5.1.10"]["downloads"]) == 1
    checked = 0
    for item in items.values():
        for d in item["downloads"]:
            r = client.get(d["path"], headers=curator_headers)
            assert r.status_code == 200, f"{item['code']} {d['label']}: {r.status_code} {r.text[:200]}"
            assert d["filename"].endswith((".docx", ".pdf", ".xlsx"))
            checked += 1
    assert checked >= 10


def test_empty_group_documents_are_blank_not_missing(client, curator_headers, curator_group):
    items = _items(client, curator_headers, curator_group)
    assert items["5.1.1"]["state"] == "blank" and items["5.1.1"]["downloads"]
    assert items["5.1.7"]["state"] == "blank" and items["5.1.7"]["downloads"] == []
    assert items["5.1.13"]["state"] == "blank" and len(items["5.1.13"]["downloads"]) == 2


def test_months_run_from_september_to_today():
    assert folder_service.months_of_year("2026-2027", datetime.date(2026, 11, 3)) == [(2026, 9), (2026, 10), (2026, 11)]
    assert folder_service.months_of_year("2025-2026", datetime.date(2026, 11, 3))[-1] == (2026, 8)
    assert len(folder_service.months_of_year("2025-2026", datetime.date(2026, 11, 3))) == 12
    assert folder_service.months_of_year("2026-2027", datetime.date(2026, 8, 20)) == []


def test_other_curator_and_anonymous_are_refused(client, curator_headers, curator_group, db_second_curator):
    assert client.get(f"/folder/groups/{curator_group.id}").status_code == 401
    other = client.post("/auth/login", json={"username": db_second_curator.username, "password": "SecondCura#58x!"}).json()
    r = _folder(client, {"Authorization": f"Bearer {other['access_token']}"}, curator_group)
    assert r.status_code == 403
    assert client.get(f"/folder/groups/{curator_group.id}/ivpr.docx",
                      headers={"Authorization": f"Bearer {other['access_token']}"}).status_code == 403


@pytest.mark.parametrize("headers_name", ["admin_headers", "edu_department_headers"])
def test_college_wide_roles_see_any_group(request, client, curator_group, headers_name):
    headers = request.getfixturevalue(headers_name)
    assert _folder(client, headers, curator_group).status_code == 200


def test_unknown_group_and_bad_year(client, curator_headers, curator_group):
    assert client.get("/folder/groups/999999", headers=curator_headers).status_code in (403, 404)
    assert _folder(client, curator_headers, curator_group, year="26-27").status_code == 422


def test_disabled_modules_show_as_off_without_downloads(client, curator_headers, curator_group, monkeypatch):
    monkeypatch.setattr(get_settings(), "enabled_modules", MINIMAL)
    items = _items(client, curator_headers, curator_group)
    for code in ("5.1.1", "5.1.3", "5.1.4", "5.1.6", "5.1.7", "5.1.8–5.1.9", "5.1.10", "5.1.11", "5.1.13"):
        assert items[code]["state"] == "off" and items[code]["downloads"] == []
    assert items["5.1.12"]["downloads"]  # табель посещаемости — модуль «Посещаемость», он включён всегда
    assert client.get(f"/folder/groups/{curator_group.id}/ivpr.docx", headers=curator_headers).status_code == 404


def test_ivpr_lists_only_students_on_internal_record_and_logs_access(client, curator_headers, curator_user, curator_group, db, today):
    first, second = _students(db, curator_group)[:2]
    r = client.put(f"/students/{first.id}/dossier/profile", headers=curator_headers, json={"special": {"internal_record": True}})
    assert r.status_code == 200, r.text
    client.post(f"/students/{first.id}/dossier/notes", headers=curator_headers,
                json={"kind": "conversation", "text": "Беседа", "goal": "Выяснить причины пропусков",
                      "result": "Договорились о справках", "occurred_on": today.isoformat()})
    r = client.get(f"/folder/groups/{curator_group.id}/ivpr.docx", headers=curator_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = _text(r.content)
    assert first.full_name in text and second.full_name not in text
    assert "Выяснить причины пропусков" in text and "Договорились о справках" in text and "Беседа" in text
    assert "студентов на внутреннем учёте: 1" in text
    logged = {row.student_id for row in db.query(DossierAccessLog).filter_by(user_id=curator_user.id, included_special=True)}
    assert logged == {first.id}
    assert db.query(AuditLog).filter_by(action="folder.ivpr_docx").count() == 1


def test_ivpr_without_students_on_internal_record_says_so(client, curator_headers, curator_group):
    r = client.get(f"/folder/groups/{curator_group.id}/ivpr.docx", headers=curator_headers)
    assert r.status_code == 200
    assert "нет студентов на внутреннем учёте" in _text(r.content)
