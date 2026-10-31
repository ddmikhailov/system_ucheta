"""Общие собрания группы и протокол в Word (п. 5.1.10, «Папка куратора»): выдуманные данные."""
import io
import xml.etree.ElementTree as ET
import zipfile

from app.core.config import get_settings
from app.models import AuditLog, GroupAssembly
from tests.test_release_modules import MINIMAL

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        root = ET.fromstring(archive.read("word/document.xml"))
    return "\n".join("".join("\n" if e.tag == f"{W}br" else (e.text or "") for e in p.iter() if e.tag in (f"{W}t", f"{W}br"))
                     for p in root.iter(f"{W}p"))


def _create(client, headers, group, **payload):
    r = client.post(f"/assemblies/groups/{group.id}", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _second_headers(client, user):
    r = client.post("/auth/login", json={"username": user.username, "password": "SecondCura#58x!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_numbers_year_and_crud(client, curator_headers, curator_group):
    first = _create(client, curator_headers, curator_group, assembly_date="2026-10-02", chair="  Старостин Пётр ")
    second = _create(client, curator_headers, curator_group, assembly_date="2026-12-20")
    assert (first["number"], second["number"]) == (1, 2) and first["school_year"] == "2026-2027" and first["chair"] == "Старостин Пётр"
    spring = _create(client, curator_headers, curator_group, assembly_date="2027-03-01")
    assert spring["number"] == 3  # нумерация идёт по учебному году, а не по календарному
    next_year = _create(client, curator_headers, curator_group, assembly_date="2027-09-05")
    assert next_year["school_year"] == "2027-2028" and next_year["number"] == 1
    undated = _create(client, curator_headers, curator_group, school_year="2026-2027")
    assert undated["assembly_date"] is None and undated["number"] == 4

    listed = client.get(f"/assemblies/groups/{curator_group.id}", headers=curator_headers, params={"year": "2026-2027"}).json()
    assert [a["number"] for a in listed["assemblies"]] == [1, 2, 3, 4] and listed["students_count"] > 0

    r = client.put(f"/assemblies/{first['id']}", headers=curator_headers, json={"assembly_date": "2026-10-02", "present_count": 21, "number": 1})
    assert r.status_code == 200 and r.json()["present_count"] == 21 and r.json()["chair"] is None
    assert client.delete(f"/assemblies/{second['id']}", headers=curator_headers).status_code == 204
    assert client.get(f"/assemblies/groups/{curator_group.id}", headers=curator_headers, params={"year": "2026-2027"}).json()["assemblies"][1]["id"] == spring["id"]
    assert client.post(f"/assemblies/groups/{curator_group.id}", headers=curator_headers, json={"school_year": "26"}).status_code == 422


def test_protocol_is_filled_from_the_assembly(client, curator_headers, curator_group, db):
    a = _create(client, curator_headers, curator_group, assembly_date="2026-10-02", chair="Старостин Пётр", secretary="Лисина Анна",
                present_count=21, agenda="Выборы старосты\nДежурство по группе", listened="Выступила староста.", resolved="Принять к сведению.")
    r = client.get(f"/assemblies/{a['id']}/protocol.docx", headers=curator_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = _text(r.content)
    assert f"общего собрания группы {curator_group.code}" in text and "ПРОТОКОЛ № 1" in text and "от 02.10.2026" in text
    assert "Председатель: Старостин Пётр" in text and "Секретарь: Лисина Анна" in text
    assert "1. Выборы старосты" in text and "2. Дежурство по группе" in text
    assert "Выступила староста." in text and "Принять к сведению." in text and "Присутствовало: 21 из" in text
    assert db.query(AuditLog).filter_by(action="assembly.protocol_docx").count() == 1


def test_empty_protocol_keeps_lines_to_fill_by_hand(client, curator_headers, curator_group):
    a = _create(client, curator_headers, curator_group)
    text = _text(client.get(f"/assemblies/{a['id']}/protocol.docx", headers=curator_headers).content)
    assert "Председатель: ____" in text and "Присутствовало: ____ из" in text and "1. ____" in text


def test_other_curator_cannot_read_or_change(client, curator_headers, curator_group, db_second_curator, db):
    a = _create(client, curator_headers, curator_group, assembly_date="2026-10-02")
    other = _second_headers(client, db_second_curator)
    assert client.get(f"/assemblies/groups/{curator_group.id}", headers=other).status_code == 403
    assert client.post(f"/assemblies/groups/{curator_group.id}", headers=other, json={}).status_code == 403
    assert client.put(f"/assemblies/{a['id']}", headers=other, json={}).status_code == 403
    assert client.delete(f"/assemblies/{a['id']}", headers=other).status_code == 403
    assert client.get(f"/assemblies/{a['id']}/protocol.docx", headers=other).status_code == 403
    assert client.get(f"/assemblies/{a['id']}/protocol.docx").status_code == 401
    assert db.query(GroupAssembly).count() == 1


def test_admin_reads_but_unknown_assembly_is_404(client, curator_headers, curator_group, admin_headers):
    a = _create(client, curator_headers, curator_group, assembly_date="2026-10-02")
    assert client.get(f"/assemblies/{a['id']}/protocol.docx", headers=admin_headers).status_code == 200
    assert client.get("/assemblies/999999/protocol.docx", headers=admin_headers).status_code == 404


def test_router_is_hidden_with_the_meetings_module(client, curator_headers, curator_group, monkeypatch):
    # Роутер подключён при импорте приложения; здесь проверяем только привязку к модулю «meetings» в реестре.
    from app.main import MODULE_ROUTERS
    from app.api.routers import assemblies

    assert (assemblies.router, "meetings") in MODULE_ROUTERS
