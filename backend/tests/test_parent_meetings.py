"""Родительские собрания и протокол в Word (этап 10): выдуманные данные."""
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from app.models import AuditLog, ParentMeeting, Student, StudyGroup

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _students(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).order_by(Student.last_name, Student.first_name).all()


def _xml(content: bytes) -> tuple[ET.Element, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        xml = archive.read("word/document.xml").decode("utf-8")
    return ET.fromstring(xml), xml


def _text(element) -> str:
    return "".join(t.text or "" for t in element.iter(f"{W}t"))


def _paragraphs(content: bytes) -> list[str]:
    root, _ = _xml(content)
    return [_text(p) for p in root.iter(f"{W}p")]


def _guardian(client, headers, student, name, relation="мать"):
    r = client.post(f"/students/{student.id}/dossier/guardians", headers=headers, json={"full_name": name, "relation": relation})
    assert r.status_code in (200, 201), r.text


def _guardian_ids(client, headers, group):
    return {g["full_name"]: g["id"] for g in client.get(f"/meetings/groups/{group.id}", headers=headers).json()["guardians"]}


def _create(client, headers, group, **payload):
    r = client.post(f"/meetings/groups/{group.id}", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_numbers_year_and_crud(client, curator_headers, curator_group, db):
    first = _create(client, curator_headers, curator_group, meeting_date="2026-10-02", agenda="Итоги месяца")
    second = _create(client, curator_headers, curator_group, meeting_date="2026-12-20")
    assert (first["number"], second["number"]) == (1, 2) and first["school_year"] == "2026-2027" and first["meeting_format"] == "in_person"
    other_year = _create(client, curator_headers, curator_group, meeting_date="2026-05-10")
    assert other_year["school_year"] == "2025-2026" and other_year["number"] == 1  # нумерация — в пределах учебного года
    manual = _create(client, curator_headers, curator_group, number=7, meeting_date="2027-03-01")
    assert manual["number"] == 7

    listed = client.get(f"/meetings/groups/{curator_group.id}?year=2026-2027", headers=curator_headers).json()
    assert [m["number"] for m in listed["meetings"]] == [1, 2, 7]
    r = client.put(f"/meetings/{first['id']}", headers=curator_headers, json={
        "meeting_date": "2026-10-03", "agenda": "Новое", "meeting_format": "remote", "listened": "Слушали", "resolved": "Постановили"})
    assert r.status_code == 200 and r.json()["meeting_format"] == "remote" and r.json()["number"] == 1
    assert client.delete(f"/meetings/{first['id']}", headers=curator_headers).status_code == 204
    assert db.get(ParentMeeting, first["id"]) is None


def test_validation(client, curator_headers, admin_headers, curator_group):
    base = f"/meetings/groups/{curator_group.id}"
    assert client.post(base, headers=curator_headers, json={"meeting_format": "hybrid"}).status_code == 422
    assert client.post(base, headers=curator_headers, json={"number": 0}).status_code == 422
    assert client.post(base, headers=curator_headers, json={"parents_count": -1}).status_code == 422
    assert client.post(base, headers=curator_headers, json={"school_year": "2026-2028"}).status_code == 422
    assert client.get(base + "?year=2026", headers=curator_headers).status_code == 422
    assert client.get("/meetings/groups/999999", headers=admin_headers).status_code == 404


def test_access_rules(client, curator_headers, admin_headers, curator_group, db):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    mine = _create(client, curator_headers, curator_group)
    foreign = _create(client, admin_headers, other)
    assert client.get(f"/meetings/groups/{curator_group.id}").status_code == 401
    assert client.get(f"/meetings/groups/{other.id}", headers=curator_headers).status_code == 403
    assert client.post(f"/meetings/groups/{other.id}", headers=curator_headers, json={}).status_code == 403
    assert client.put(f"/meetings/{foreign['id']}", headers=curator_headers, json={}).status_code == 403
    assert client.delete(f"/meetings/{foreign['id']}", headers=curator_headers).status_code == 403
    assert client.put(f"/meetings/{foreign['id']}/attendance", headers=curator_headers, json={"guardian_ids": []}).status_code == 403
    assert client.get(f"/meetings/{foreign['id']}/protocol.docx", headers=curator_headers).status_code == 403
    assert client.get(f"/meetings/groups/{curator_group.id}", headers=admin_headers).json()["meetings"][0]["id"] == mine["id"]
    assert client.put("/meetings/999999", headers=admin_headers, json={}).status_code == 404


def test_guardians_listed_for_the_group_only_and_without_phones(client, curator_headers, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    stranger = db.query(Student).filter_by(study_group_id=other_group.id).first()
    client.post(f"/students/{a.id}/dossier/guardians", headers=curator_headers, json={"full_name": "Иванова Мария", "relation": "мать", "phone": "+7 900 000-00-01"})
    _guardian(client, curator_headers, b, "Петров Пётр", "отец")
    # чужого представителя куратор добавить не может — берём напрямую из БД
    from app.models import StudentGuardian
    foreign = StudentGuardian(student_id=stranger.id, full_name="Чужая Мать", relation="мать")
    db.add(foreign)
    db.commit()
    data = client.get(f"/meetings/groups/{curator_group.id}", headers=curator_headers).json()
    assert {g["full_name"] for g in data["guardians"]} == {"Иванова Мария", "Петров Пётр"}
    first = next(g for g in data["guardians"] if g["full_name"] == "Иванова Мария")
    assert first["student_name"] == a.full_name and first["relation"] == "мать" and "phone" not in first

    m = _create(client, curator_headers, curator_group)
    bad = client.put(f"/meetings/{m['id']}/attendance", headers=curator_headers, json={"guardian_ids": [foreign.id]})
    assert bad.status_code == 400


def test_protocol_is_filled_from_the_meeting(client, curator_headers, curator_group, db):
    a, b = _students(db, curator_group)[:2]
    _guardian(client, curator_headers, a, "Иванова Мария")
    _guardian(client, curator_headers, b, "Петров Пётр", "отец")
    ids = _guardian_ids(client, curator_headers, curator_group)
    m = _create(client, curator_headers, curator_group, meeting_date="2026-10-02", agenda="Итоги месяца\nПосещаемость",
                staff="Иванов И.И., зав. отделением", speakers="Сидоров С.С., инспектор ПДН", meeting_format="remote",
                listened="Обсудили итоги.\nЗаслушали инспектора.", resolved="Усилить контроль посещаемости.")
    r = client.put(f"/meetings/{m['id']}/attendance", headers=curator_headers, json={"guardian_ids": [ids["Петров Пётр"], ids["Иванова Мария"], ids["Иванова Мария"]]})
    assert r.status_code == 200 and len(r.json()["attendee_ids"]) == 2

    r = client.get(f"/meetings/{m['id']}/protocol.docx", headers=curator_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = _paragraphs(r.content)
    assert "«02» октября 2026 г." in text and "ПРОТОКОЛ РОДИТЕЛЬСКОГО СОБРАНИЯ №1" in text
    assert f"Группа {curator_group.code}" in text
    assert "1. Итоги месяца" in text and "2. Посещаемость" in text
    assert "1. Иванов И.И., зав. отделением" in text and "1. Сидоров С.С., инспектор ПДН" in text
    assert "Присутствовало количество родителей/законных представителей: 2" in text
    assert "Обсудили итоги.\nЗаслушали инспектора." not in text  # перенос строки — разрыв внутри абзаца, а не символ
    assert any(p.startswith("Обсудили итоги.") and "Заслушали инспектора." in p for p in text)
    assert "Усилить контроль посещаемости." in text and not any(p.startswith("1…") or p == "2…" for p in text)
    root, xml = _xml(r.content)
    fmt = next(p for p in root.iter(f"{W}p") if _text(p).startswith("Формат проведения"))
    assert {_text(run) for run in fmt.iter(f"{W}r") if run.find(f"{W}rPr/{W}u") is not None} == {"дистанционный"}
    rows = [[_text(c) for c in tr.findall(f"{W}tc")] for tr in next(root.iter(f"{W}tbl")).findall(f"{W}tr")]
    assert len(rows) == 31 and rows[1][:3] == ["1", "Иванова Мария", "02.10.2026"] and rows[2][1] == "Петров Пётр"
    assert rows[3][1] == "" and rows[30][0] == "30"
    assert "соцвыплата" not in xml
    ids_xml = re.findall(r'w14:paraId="([0-9A-F]+)"', xml)
    assert len(ids_xml) == len(set(ids_xml))


def test_protocol_without_details_keeps_blank_lines(client, curator_headers, curator_group):
    m = _create(client, curator_headers, curator_group)
    text = _paragraphs(client.get(f"/meetings/{m['id']}/protocol.docx", headers=curator_headers).content)
    assert "ПРОТОКОЛ РОДИТЕЛЬСКОГО СОБРАНИЯ №1" in text
    assert any(p.startswith("«___»") for p in text) and text.count("1…") == 3 and text.count("2…") == 3
    assert any(p.startswith("Присутствовало количество родителей/законных представителей: _") for p in text)
    assert "СЛУШАЛИ" in text and "ПОСТАНОВИЛИ" in text


def test_manual_parents_count_used_when_nobody_was_checked(client, curator_headers, curator_group):
    m = _create(client, curator_headers, curator_group, parents_count=17, meeting_format="in_person")
    r = client.get(f"/meetings/{m['id']}/protocol.docx", headers=curator_headers)
    text = _paragraphs(r.content)
    assert "Присутствовало количество родителей/законных представителей: 17" in text
    root, _ = _xml(r.content)
    fmt = next(p for p in root.iter(f"{W}p") if _text(p).startswith("Формат проведения"))
    assert {_text(run) for run in fmt.iter(f"{W}r") if run.find(f"{W}rPr/{W}u") is not None} == {"очный"}


def test_more_than_thirty_parents_and_escaping(client, curator_headers, curator_group, db):
    from app.services import parent_meeting_service as svc
    m = _create(client, curator_headers, curator_group, agenda='Вопрос "А" & <Б>')
    meeting = db.get(ParentMeeting, m["id"])
    content = svc.build_protocol_docx(meeting=meeting, group_code="Т1", curator_name='К & "Ж"', parents=[f"Родитель {i:02d}" for i in range(1, 34)])
    root, _ = _xml(content)
    rows = [[_text(c) for c in tr.findall(f"{W}tc")] for tr in next(root.iter(f"{W}tbl")).findall(f"{W}tr")]
    assert len(rows) == 34 and rows[33][:2] == ["33", "Родитель 33"]
    text = [_text(p) for p in root.iter(f"{W}p")]
    assert '1. Вопрос "А" & <Б>' in text and 'Куратор группы К & "Ж"' in text


def test_actions_are_audited(client, curator_headers, curator_user, curator_group, db):
    m = _create(client, curator_headers, curator_group)
    client.put(f"/meetings/{m['id']}/attendance", headers=curator_headers, json={"guardian_ids": []})
    client.get(f"/meetings/{m['id']}/protocol.docx", headers=curator_headers)
    client.delete(f"/meetings/{m['id']}", headers=curator_headers)
    actions = {a.action for a in db.query(AuditLog).filter(AuditLog.user_id == curator_user.id)}
    assert {"meeting.create", "meeting.attendance", "meeting.protocol_docx", "meeting.delete"} <= actions
