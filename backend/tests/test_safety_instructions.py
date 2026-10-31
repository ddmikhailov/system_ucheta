"""Журнал инструктажа по охране труда (п. 5.1.15) и бланк для подписей: выдуманные данные."""
import io
import xml.etree.ElementTree as ET
import zipfile

from app.core.time import today_local
from app.models import AuditLog, SafetyInstruction, StudyGroup
from app.services import attendance_service

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _create(client, headers, group, **payload):
    body = {"instruction_date": "2026-09-03", "kind": "introductory", "topic": "Правила поведения в колледже", **payload}
    r = client.post(f"/instructions/groups/{group.id}", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _doc(content: bytes):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        return ET.fromstring(archive.read("word/document.xml"))


def _text(element) -> str:
    return "".join(t.text or "" for t in element.iter(f"{W}t"))


def test_crud_and_school_year(client, curator_headers, curator_group, db):
    first = _create(client, curator_headers, curator_group, conducted_by="  Куратор К.К.  ")
    assert first["school_year"] == "2026-2027" and first["kind_label"] == "Вводный" and first["conducted_by"] == "Куратор К.К."
    spring = _create(client, curator_headers, curator_group, instruction_date="2027-05-20", kind="targeted", topic="Выезд на экскурсию")
    old = _create(client, curator_headers, curator_group, instruction_date="2026-05-20")
    assert old["school_year"] == "2025-2026"

    listed = client.get(f"/instructions/groups/{curator_group.id}?year=2026-2027", headers=curator_headers).json()
    assert [r["id"] for r in listed["instructions"]] == [first["id"], spring["id"]] and listed["can_edit"] is True
    assert set(listed["kinds"]) == {"introductory", "primary", "repeated", "targeted", "unplanned"}

    r = client.put(f"/instructions/{first['id']}", headers=curator_headers, json={
        "instruction_date": "2026-09-04", "kind": "primary", "topic": "Новая тема", "note": "С опозданием"})
    assert r.status_code == 200 and r.json()["kind"] == "primary" and r.json()["note"] == "С опозданием" and r.json()["conducted_by"] is None
    assert client.delete(f"/instructions/{first['id']}", headers=curator_headers).status_code == 204
    assert db.get(SafetyInstruction, first["id"]) is None
    actions = {a.action for a in db.query(AuditLog).all()}
    assert {"instruction.create", "instruction.update", "instruction.delete"} <= actions


def test_validation(client, curator_headers, admin_headers, curator_group):
    base = f"/instructions/groups/{curator_group.id}"
    good = {"instruction_date": "2026-09-03", "kind": "introductory", "topic": "Тема"}
    assert client.post(base, headers=curator_headers, json={**good, "kind": "other"}).status_code == 422
    assert client.post(base, headers=curator_headers, json={**good, "topic": ""}).status_code == 422
    assert client.post(base, headers=curator_headers, json={**good, "topic": "   "}).status_code == 422
    assert client.post(base, headers=curator_headers, json={k: v for k, v in good.items() if k != "instruction_date"}).status_code == 422
    assert client.get(base + "?year=2026", headers=curator_headers).status_code == 422
    assert client.get("/instructions/groups/999999", headers=admin_headers).status_code == 404


def test_access_rules(client, curator_headers, admin_headers, dept_head_headers, curator_group, db):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    mine = _create(client, curator_headers, curator_group)
    foreign = _create(client, admin_headers, other)
    body = {"instruction_date": "2026-09-03", "kind": "introductory", "topic": "Тема"}
    assert client.get(f"/instructions/groups/{curator_group.id}").status_code == 401
    assert client.get(f"/instructions/groups/{other.id}", headers=curator_headers).status_code == 403
    assert client.post(f"/instructions/groups/{other.id}", headers=curator_headers, json=body).status_code == 403
    assert client.put(f"/instructions/{foreign['id']}", headers=curator_headers, json=body).status_code == 403
    assert client.delete(f"/instructions/{foreign['id']}", headers=curator_headers).status_code == 403
    assert client.get(f"/instructions/{foreign['id']}/blank.docx", headers=curator_headers).status_code == 403
    assert client.get(f"/instructions/groups/{curator_group.id}", headers=admin_headers).json()["instructions"][0]["id"] == mine["id"]
    assert client.put("/instructions/999999", headers=admin_headers, json=body).status_code == 404
    # зав. отделением работает с группами своего отделения
    assert client.get(f"/instructions/groups/{curator_group.id}", headers=dept_head_headers).status_code == 200


def test_blank_has_whole_group_and_no_dossier_data(client, curator_headers, curator_group, db):
    record = _create(client, curator_headers, curator_group, kind="repeated", topic="Электробезопасность", conducted_by="Иванов И.И.", note="Перед практикой")
    r = client.get(f"/instructions/{record['id']}/blank.docx", headers=curator_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    root = _doc(r.content)
    paragraphs = [_text(p) for p in root.iter(f"{W}p")]
    assert "ЖУРНАЛ ИНСТРУКТАЖА ПО ОХРАНЕ ТРУДА" in paragraphs
    assert "Дата инструктажа: 03.09.2026" in paragraphs and "Вид инструктажа: Повторный" in paragraphs
    assert "Тема: Электробезопасность" in paragraphs and "Инструктаж провёл: Иванов И.И." in paragraphs
    assert "Примечание: Перед практикой" in paragraphs
    rows = [[_text(c) for c in tr.findall(f"{W}tc")] for tr in next(root.iter(f"{W}tbl")).findall(f"{W}tr")]
    students = attendance_service.get_active_students(db, curator_group.id, today_local())
    assert rows[0] == ["№", "ФИО", "Подпись", "Дата"]
    assert students and [row[1] for row in rows[1:]] == [s.full_name for s in students]
    assert [row[0] for row in rows[1:]] == [str(n) for n in range(1, len(rows))] and all(row[2] == row[3] == "" for row in rows[1:])
    assert db.query(AuditLog).filter_by(action="instruction.blank_docx").count() == 1


def test_edu_department_edits_its_department(client, edu_department_headers, curator_group, curator_headers):
    body = {"instruction_date": "2026-09-03", "kind": "unplanned", "topic": "Внеплановый инструктаж"}
    r = client.post(f"/instructions/groups/{curator_group.id}", headers=edu_department_headers, json=body)
    assert r.status_code == 201
    assert client.get(f"/instructions/{r.json()['id']}/blank.docx", headers=edu_department_headers).status_code == 200
    assert client.get(f"/instructions/groups/{curator_group.id}", headers=edu_department_headers).json()["can_edit"] is True
