"""«Отчёт куратора» за семестр (этап 8): выдуманные данные."""
import datetime
import io
import xml.etree.ElementTree as ET
import zipfile

from app.core.time import today_local
from app.models import AuditLog, CuratorReport, Student, StudyGroup
from app.services import calendar_service
from app.services import curator_report_service as svc
from app.services import group_event_service

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _year_semester():
    today = today_local()
    return group_event_service.school_year(today), svc.current_semester(today)


def _url(group, suffix="", **extra):
    year, semester = _year_semester()
    query = f"year={extra.get('year', year)}&semester={extra.get('semester', semester)}"
    return f"/reports/groups/{group.id}{suffix}?{query}"


def _fields(data) -> dict:
    return {f["key"]: f for s in data["sections"] for f in s["fields"]}


def _students(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).order_by(Student.last_name, Student.first_name).all()


def _text_br(element) -> str:
    return "".join("\n" if e.tag == f"{W}br" else (e.text or "") for e in element.iter() if e.tag in (f"{W}t", f"{W}br"))


def _docx(content: bytes):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        xml = archive.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(xml)
    tables = [[[_text_br(c) for c in tr.findall(f"{W}tc")] for tr in t.findall(f"{W}tr")] for t in root.iter(f"{W}tbl")]
    paragraphs = ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p")]
    return tables, paragraphs


def test_report_structure_and_basic_auto_values(client, curator_headers, curator_group, db):
    data = client.get(_url(curator_group), headers=curator_headers).json()
    assert [s["key"] for s in data["sections"]] == ["general", "movement", "individual", "documents", "events", "selfgov"]
    fields = _fields(data)
    assert fields["g_students"]["auto"] == str(len(_students(db, curator_group))) and fields["g_students"]["value"] is None
    assert data["can_edit"] is True and data["group_code"] == curator_group.code and data["semester"] in (1, 2)
    assert data["period_from"] < data["period_to"] and data["updated_at"] is None
    assert fields["g_iup"]["auto"] is None  # ИУП платформа не знает — вручную


def test_manual_values_roundtrip_per_semester_and_year(client, curator_headers, curator_group, db):
    year, semester = _year_semester()
    r = client.put(_url(curator_group), headers=curator_headers, json={"values": {"g_iup": " 2 ", "m_left_college": "1", "s_1": "Иванов И.", "g_debts": "", "g_camps": None}})
    assert r.status_code == 200
    fields = _fields(r.json())
    assert (fields["g_iup"]["value"], fields["m_left_college"]["value"], fields["s_1"]["value"]) == ("2", "1", "Иванов И.")
    assert fields["g_debts"]["value"] is None and r.json()["updated_at"] is not None

    other_semester = 2 if semester == 1 else 1
    again = client.get(_url(curator_group, semester=other_semester), headers=curator_headers).json()
    assert _fields(again)["g_iup"]["value"] is None  # у другого семестра свои цифры
    assert _fields(client.get(_url(curator_group, year="2020-2021"), headers=curator_headers).json())["g_iup"]["value"] is None

    # заменяются целиком: что не прислано — пропадает
    client.put(_url(curator_group), headers=curator_headers, json={"values": {"g_debts": "3"}})
    fields = _fields(client.get(_url(curator_group), headers=curator_headers).json())
    assert fields["g_debts"]["value"] == "3" and fields["g_iup"]["value"] is None
    assert db.query(CuratorReport).filter_by(study_group_id=curator_group.id, school_year=year, semester=semester).count() == 1


def test_validation(client, curator_headers, admin_headers, curator_group):
    assert client.put(_url(curator_group), headers=curator_headers, json={"values": {"nope": "1"}}).status_code == 400
    assert client.put(_url(curator_group), headers=curator_headers, json={"values": {"g_iup": "я" * 2001}}).status_code == 422
    assert client.get(f"/reports/groups/{curator_group.id}?year=2026", headers=curator_headers).status_code == 422
    assert client.get(f"/reports/groups/{curator_group.id}?semester=3", headers=curator_headers).status_code == 422
    assert client.get("/reports/groups/999999", headers=admin_headers).status_code == 404


def test_access_rules(client, curator_headers, admin_headers, curator_group, db):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    assert client.get(_url(curator_group)).status_code == 401
    assert client.get(_url(other), headers=curator_headers).status_code == 403
    assert client.put(_url(other), headers=curator_headers, json={"values": {}}).status_code == 403
    assert client.get(_url(other, "/report.docx"), headers=curator_headers).status_code == 403
    assert client.get(_url(other, "/report.docx"), headers=admin_headers).status_code == 200


def test_auto_values_from_events_meetings_notes_and_attendance(client, curator_headers, curator_group, db, today):
    year, semester = _year_semester()
    start, end = svc.period(year, semester)
    inside = max(start, min(end, today_local()))
    s = _students(db, curator_group)[0]
    for title, date, status_ in (("Урок мужества", inside, "done"), ("Планируемое", inside, "planned")):
        r = client.post(f"/events/groups/{curator_group.id}", headers=curator_headers,
                        json={"section": "civic", "title": title, "event_date": date.isoformat(), "status": status_})
        assert r.status_code == 201
    r = client.post(f"/meetings/groups/{curator_group.id}", headers=curator_headers, json={"meeting_date": inside.isoformat(), "meeting_format": "in_person"})
    assert r.status_code == 201
    client.post(f"/students/{s.id}/dossier/notes", headers=curator_headers, json={"kind": "parent_invited", "text": "Вызвали маму"})
    client.post(f"/students/{s.id}/dossier/notes", headers=curator_headers, json={"kind": "incident", "text": "Не считается"})

    days = calendar_service.study_days_between(db, today - datetime.timedelta(days=21), today, study_group_id=curator_group.id, course=curator_group.course)
    day = days[-1]
    if start <= day <= end:
        r = client.post(f"/curator/groups/{curator_group.id}/day/submit?date={day}", headers=curator_headers, json={
            "exceptions": [{"student_id": s.id, "mark_code": "н", "comment": None, "basis_reference": None}]})
        assert r.status_code == 200, r.text

    fields = _fields(client.get(_url(curator_group), headers=curator_headers).json())
    assert fields["ev_civic_cp"]["auto"] == "1" and "Урок мужества" in fields["ev_civic_comment"]["auto"]
    assert "Планируемое" not in fields["ev_civic_comment"]["auto"]  # только проведённые
    assert fields["i_parent_meetings"]["auto"] == "1" and fields["i_meetings"]["auto"] == "2"  # собрание очно + вызов родителей
    assert fields["ev_parents_c"]["auto"] == "1"  # вызов родителей; «инцидент» не считается
    assert fields["d_plan"]["auto"] == "Есть" and fields["d_passport"]["auto"].startswith("Есть")
    if start <= day <= end:
        assert fields["g_unexcused"]["auto"].endswith(" %")


def test_future_semester_has_no_auto_values_and_past_year_still_loads(client, curator_headers, curator_group):
    future = _fields(client.get(_url(curator_group, year="2099-2100", semester=1), headers=curator_headers).json())
    assert all(f["auto"] is None for f in future.values())
    assert client.get(_url(curator_group, year="2020-2021", semester=2), headers=curator_headers).status_code == 200


def test_word_report_uses_manual_values_over_auto_and_keeps_blanks(client, curator_headers, curator_group, db):
    year, semester = _year_semester()
    client.put(_url(curator_group), headers=curator_headers, json={"values": {
        "g_students": "99", "g_iup": "2", "m_left_college": "2", "m_left_failure": "1", "i_vku": "1", "i_vku_removed": "0",
        "d_cards": "Да", "s_1": "Иванов И., Петров П.", "ev_instructions_c": "2", "ev_instructions_v": "25",
        "ev_civic_cp": "4", "ev_civic_comment": "Акция «Окна Победы»"}})
    r = client.get(_url(curator_group, "/report.docx"), headers=curator_headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "%D0%9E%D1%82%D1%87%D1%91%D1%82" in r.headers["content-disposition"] or "filename*=UTF-8''" in r.headers["content-disposition"]
    tables, paragraphs = _docx(r.content)
    numeral = "I" if semester == 1 else "II"
    first, second = year.split("-")
    assert f"ЗА {numeral} СЕМЕСТР {first}/{second} УЧЕБНОГО ГОДА" in paragraphs and f"{curator_group.code} УЧЕБНОЙ ГРУППЫ" in paragraphs
    general, movement, individual, documents, events, selfgov = tables
    assert general[1][1] == "99"  # внесённое важнее посчитанного
    assert general[3][1] == "2" and general[4][1] == ""  # задолженности не вносили — пусто
    assert movement[2][1] == "2\n1" and movement[1][1] == ""
    assert individual[1][1] == "1\n—\n0\n—"  # подпункты по строкам, пропущенные — тире
    assert documents[3][1] == "Да"
    assert selfgov[1][2] == "Иванов И., Петров П." and selfgov[2][2] == ""
    civic = next(row for row in events if row and row[0] == "1.1")
    assert civic[2] == "4" and civic[-1] == "Акция «Окна Победы»"
    instructions = next(row for row in events if row and row[0] == "4.1")
    assert instructions[2:4] == ["2", "25"]
    assert len(selfgov) == 10 and len(events) == 15  # структура образца сохранена


def test_word_report_without_any_values_is_a_clean_blank(client, curator_headers, curator_group):
    tables, paragraphs = _docx(client.get(_url(curator_group, "/report.docx", year="2099-2100", semester=2), headers=curator_headers).content)
    assert "ЗА II СЕМЕСТР 2099/2100 УЧЕБНОГО ГОДА" in paragraphs
    assert all(row[1] == "" for row in tables[0][1:]) and all(row[2] == "" for row in tables[5][1:])


def test_actions_are_audited_without_values(client, curator_headers, curator_user, curator_group, db):
    client.put(_url(curator_group), headers=curator_headers, json={"values": {"g_iup": "секретное-значение", "s_1": "Иванов"}})
    client.get(_url(curator_group, "/report.docx"), headers=curator_headers)
    entries = db.query(AuditLog).filter(AuditLog.user_id == curator_user.id, AuditLog.action.in_(["report.save", "report.docx"])).all()
    assert {e.action for e in entries} == {"report.save", "report.docx"}
    saved = next(e for e in entries if e.action == "report.save")
    assert saved.new_value.endswith(":2") and all("секретное" not in (e.new_value or "") for e in entries)


def test_semester_periods():
    assert svc.period("2026-2027", 1) == (datetime.date(2026, 9, 1), datetime.date(2027, 1, 31))
    assert svc.period("2026-2027", 2) == (datetime.date(2027, 2, 1), datetime.date(2027, 8, 31))
    assert [svc.current_semester(datetime.date(2026, m, 15)) for m in (9, 12)] + [svc.current_semester(datetime.date(2027, m, 15)) for m in (1, 2, 6)] == [1, 1, 1, 2, 2]
