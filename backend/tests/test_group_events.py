"""План воспитательной работы группы и протокол классного часа (этап 9): выдуманные данные."""
import datetime
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from app.models import AuditLog, GroupEvent, Student, StudyGroup
from app.services import group_event_service as svc

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


def _text_br(element) -> str:
    """Текст с переводами строк (разрыв строки внутри ячейки — «\n»)."""
    return "".join("\n" if e.tag == f"{W}br" else (e.text or "") for e in element.iter() if e.tag in (f"{W}t", f"{W}br"))


def _paragraphs(content: bytes) -> list[str]:
    root, _ = _xml(content)
    return [_text(p) for p in root.iter(f"{W}p")]


def _plan_rows(content: bytes) -> list[dict]:
    """Строки таблицы плана: заголовки разделов и строки мероприятий (текст ячеек)."""
    root, _ = _xml(content)
    rows = []
    for tr in next(root.iter(f"{W}tbl")).findall(f"{W}tr"):
        cells = tr.findall(f"{W}tc")
        if len(cells) == 1:
            rows.append({"section": _text(cells[0]).strip()})
        else:
            rows.append({"cells": [_text_br(c) for c in cells]})
    return rows[1:]


def _create(client, headers, group, **payload):
    body = {"section": "civic", "title": "Урок мужества", **payload}
    r = client.post(f"/events/groups/{group.id}", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_event_crud_and_year_from_date(client, curator_headers, curator_group, db):
    e = _create(client, curator_headers, curator_group, event_date="2026-10-14", time_text="14:30",
                responsible="Куратор", goal="Патриотизм", status="planned")
    assert e["school_year"] == "2026-2027" and e["time_text"] == "14:30" and e["attendee_ids"] == []
    spring = _create(client, curator_headers, curator_group, title="Весенний", event_date="2027-03-10")
    assert spring["school_year"] == "2026-2027"
    old = _create(client, curator_headers, curator_group, title="Прошлогодний", event_date="2026-05-20")
    assert old["school_year"] == "2025-2026"

    plan = client.get(f"/events/groups/{curator_group.id}?year=2026-2027", headers=curator_headers).json()
    assert [x["title"] for x in plan["events"]] == ["Урок мужества", "Весенний"]  # по дате
    assert plan["can_edit"] is True and plan["group_code"] == curator_group.code
    assert plan["years"][:2] == ["2026-2027", "2025-2026"] and len(plan["sections"]) == 11
    assert len(plan["students"]) == len(_students(db, curator_group))

    r = client.put(f"/events/{e['id']}", headers=curator_headers, json={
        "section": "legal", "title": "Беседа о праве", "status": "done", "result": "Прошло хорошо", "event_date": "2026-10-14"})
    assert r.status_code == 200 and r.json()["section"] == "legal" and r.json()["status"] == "done"
    assert client.delete(f"/events/{e['id']}", headers=curator_headers).status_code == 204
    assert db.get(GroupEvent, e["id"]) is None


def test_validation(client, curator_headers, admin_headers, curator_group):
    base = f"/events/groups/{curator_group.id}"
    assert client.post(base, headers=curator_headers, json={"section": "nope", "title": "x"}).status_code == 422
    assert client.post(base, headers=curator_headers, json={"section": "civic", "title": ""}).status_code == 422
    assert client.post(base, headers=curator_headers, json={"section": "civic", "title": "x", "status": "bad"}).status_code == 422
    assert client.post(base, headers=curator_headers, json={"section": "civic", "title": "x", "school_year": "2026-2028"}).status_code == 422
    assert client.get(base + "?year=2026", headers=curator_headers).status_code == 422
    assert client.get("/events/groups/999999", headers=admin_headers).status_code == 404


def test_access_rules(client, curator_headers, admin_headers, curator_group, db):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    mine = _create(client, curator_headers, curator_group)
    assert client.get(f"/events/groups/{curator_group.id}").status_code == 401
    assert client.get(f"/events/groups/{other.id}", headers=curator_headers).status_code == 403
    assert client.post(f"/events/groups/{other.id}", headers=curator_headers, json={"section": "civic", "title": "x"}).status_code == 403
    foreign = _create(client, admin_headers, other, title="Чужое")
    assert client.put(f"/events/{foreign['id']}", headers=curator_headers, json={"section": "civic", "title": "взлом"}).status_code == 403
    assert client.delete(f"/events/{foreign['id']}", headers=curator_headers).status_code == 403
    assert client.get(f"/events/{foreign['id']}/protocol.docx", headers=curator_headers).status_code == 403
    assert client.get(f"/events/groups/{other.id}/plan.docx", headers=curator_headers).status_code == 403
    assert client.get(f"/events/groups/{curator_group.id}", headers=admin_headers).json()["events"][0]["id"] == mine["id"]
    assert client.put("/events/999999", headers=admin_headers, json={"section": "civic", "title": "x"}).status_code == 404


def test_plan_docx_places_events_in_sections_and_keeps_blank_rows(client, curator_headers, curator_group, db):
    _create(client, curator_headers, curator_group, title="Второй", event_date="2026-11-02", time_text="12:00",
            responsible="Иванов И.И.", goal="Цель второго", status="done", result="Прошло")
    _create(client, curator_headers, curator_group, title="Первый", event_date="2026-10-01", status="cancelled", result="болезнь")
    _create(client, curator_headers, curator_group, title="Без даты", section="parents")
    _create(client, curator_headers, curator_group, title="Весной", event_date="2027-04-01", section="parents")
    _create(client, curator_headers, curator_group, title="Прошлогоднее", event_date="2026-05-01")
    r = client.get(f"/events/groups/{curator_group.id}/plan.docx?kind=group&year=2026-2027", headers=curator_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    rows = _plan_rows(r.content)
    sections = [i for i, row in enumerate(rows) if "section" in row]
    assert len(sections) == 11 and rows[sections[0]]["section"] == "Гражданско - патриотическое воспитание"

    civic = [row["cells"] for row in rows[sections[0] + 1: sections[1]]]
    assert [c[0] for c in civic] == ["Первый", "Второй"]  # по дате; прошлогоднее в этот год не входит
    assert civic[0][1] == "01.10.2026" and civic[0][4] == "Отменено: болезнь"
    assert civic[1][1:] == ["02.11.2026\n12:00", "Иванов И.И.", "Цель второго", "Прошло"]
    parents = [row["cells"][0] for row in rows[sections[7] + 1: sections[8]]]
    assert parents == ["Весной", "Без даты"]  # без даты — в конце
    legal = rows[sections[1] + 1: sections[2]]
    assert len(legal) == svc.MIN_ROWS and all(not any(row["cells"]) for row in legal)  # пустой раздел — две пустые строки
    assert "Прошлогоднее" not in " ".join(_paragraphs(r.content))


def test_plan_titles_for_group_and_curator_forms(client, curator_headers, curator_group):
    group = _paragraphs(client.get(f"/events/groups/{curator_group.id}/plan.docx?kind=group&year=2026-2027", headers=curator_headers).content)
    assert f"План воспитательной работы учебной группы {curator_group.code}" in group and "на 2026 – 2027 учебный год" in group
    curator = _paragraphs(client.get(f"/events/groups/{curator_group.id}/plan.docx?kind=curator&year=2026-2027", headers=curator_headers).content)
    assert "2026/2027 УЧЕБНОГО ГОДА" in curator and f"{curator_group.code} УЧЕБНОЙ ГРУППЫ" in curator
    assert any(p.startswith("Советник директора") for p in curator)  # три подписи образца сохранены
    assert client.get(f"/events/groups/{curator_group.id}/plan.docx?kind=other", headers=curator_headers).status_code == 422


def test_xml_escaping_and_unique_ids_in_the_plan(client, curator_headers, curator_group):
    for i in range(4):
        _create(client, curator_headers, curator_group, title=f'Акция "Я & <мы>" {i}', goal="a<b")
    r = client.get(f"/events/groups/{curator_group.id}/plan.docx", headers=curator_headers)
    _, xml = _xml(r.content)
    assert 'Акция "Я & <мы>" 0' in " ".join(_paragraphs(r.content))
    ids = re.findall(r'w14:paraId="([0-9A-F]+)"', xml)
    assert len(ids) == len(set(ids))


def test_class_hour_attendance_and_protocol(client, curator_headers, curator_group, db):
    students = _students(db, curator_group)
    e = _create(client, curator_headers, curator_group, title="Классный час «Безопасность»", section="group_org",
                event_date="2026-10-02", is_class_hour=True, description="Очно, беседа с презентацией")
    chosen = [students[1].id, students[0].id]
    r = client.put(f"/events/{e['id']}/attendance", headers=curator_headers, json={"student_ids": chosen + chosen})
    assert r.status_code == 200 and r.json()["attendee_ids"] == sorted(chosen)

    r = client.get(f"/events/{e['id']}/protocol.docx", headers=curator_headers)
    assert r.status_code == 200
    text = _paragraphs(r.content)
    assert "«02» октября 2026 г." in text and f"Группа {curator_group.code}" in text
    assert "Тема классного часа: Классный час «Безопасность»" in text
    assert f"Присутствовало обучающихся: 2 из списочного количества {len(students)}" in text
    assert "Формат и описание проведения классного часа: Очно, беседа с презентацией" in text
    root, xml = _xml(r.content)
    rows = [[_text(c) for c in tr.findall(f"{W}tc")] for tr in next(root.iter(f"{W}tbl")).findall(f"{W}tr")]
    assert len(rows) == 31
    assert rows[1][:3] == ["1", students[0].full_name, "02.10.2026"] and rows[2][1] == students[1].full_name
    assert rows[3][1] == "" and rows[30][0] == "30"  # остальные строки — для записи от руки
    ids = re.findall(r'w14:paraId="([0-9A-F]+)"', xml)
    assert len(ids) == len(set(ids))


def test_protocol_without_attendance_keeps_blanks_and_rejects_other_events(client, curator_headers, curator_group, db):
    e = _create(client, curator_headers, curator_group, title="Классный час", is_class_hour=True)
    text = _paragraphs(client.get(f"/events/{e['id']}/protocol.docx", headers=curator_headers).content)
    assert any(p.startswith("Присутствовало обучающихся: _________ из списочного количества") for p in text)
    assert any(p.startswith("Формат и описание проведения классного часа: _") for p in text)
    plain = _create(client, curator_headers, curator_group, title="Экскурсия")
    assert client.get(f"/events/{plain['id']}/protocol.docx", headers=curator_headers).status_code == 400
    assert client.put(f"/events/{plain['id']}/attendance", headers=curator_headers, json={"student_ids": []}).status_code == 400


def test_protocol_with_more_than_thirty_present(client, curator_headers, curator_group, db):
    students = _students(db, curator_group)
    e = _create(client, curator_headers, curator_group, title="Большой классный час", is_class_hour=True)
    # студентов в группе меньше 30 — проверяем разбор шаблона напрямую
    present = [f"Студент {i:02d}" for i in range(1, 36)]
    event = db.get(GroupEvent, e["id"])
    content = svc.build_protocol_docx(event=event, group_code="Т1", curator_name=None, listed=len(students), present=present)
    root, _ = _xml(content)
    rows = [[_text(c) for c in tr.findall(f"{W}tc")] for tr in next(root.iter(f"{W}tbl")).findall(f"{W}tr")]
    assert len(rows) == 36 and rows[35][:2] == ["35", "Студент 35"]


def test_attendance_only_for_group_students_and_changing_type_clears_it(client, curator_headers, admin_headers, curator_group, db):
    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    foreign = db.query(Student).filter_by(study_group_id=other_group.id).first()
    e = _create(client, curator_headers, curator_group, title="Час", is_class_hour=True)
    bad = client.put(f"/events/{e['id']}/attendance", headers=curator_headers, json={"student_ids": [foreign.id]})
    assert bad.status_code == 400
    mine = _students(db, curator_group)[0]
    client.put(f"/events/{e['id']}/attendance", headers=curator_headers, json={"student_ids": [mine.id]})
    r = client.put(f"/events/{e['id']}", headers=curator_headers, json={"section": "civic", "title": "Час", "is_class_hour": False})
    assert r.json()["attendee_ids"] == []  # перестал быть классным часом — отметки убираются


def test_actions_are_audited(client, curator_headers, curator_user, curator_group, db):
    e = _create(client, curator_headers, curator_group, title="Час", is_class_hour=True)
    client.put(f"/events/{e['id']}/attendance", headers=curator_headers, json={"student_ids": []})
    client.get(f"/events/groups/{curator_group.id}/plan.docx", headers=curator_headers)
    client.get(f"/events/{e['id']}/protocol.docx", headers=curator_headers)
    client.delete(f"/events/{e['id']}", headers=curator_headers)
    actions = {a.action for a in db.query(AuditLog).filter(AuditLog.user_id == curator_user.id)}
    assert {"event.create", "event.attendance", "event.plan_docx", "event.protocol_docx", "event.delete"} <= actions


def test_school_year_helpers():
    assert svc.school_year(datetime.date(2026, 9, 1)) == "2026-2027" and svc.school_year(datetime.date(2027, 8, 31)) == "2026-2027"
    assert svc.school_year(datetime.date(2027, 1, 5)) == "2026-2027"
    assert svc.valid_school_year("2026-2027") and not svc.valid_school_year("2026-2028") and not svc.valid_school_year("2026")
