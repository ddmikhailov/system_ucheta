"""«Личная карточка обучающегося» в Word с выбором полей: выдуманные данные."""
import datetime
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from app.core.time import today_local
from app.models import AuditLog, Student, StudyGroup
from app.services import calendar_service, student_card_service as svc

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ALL_FIELDS = "full_name,group,gender,birth_date,birth_place,registration_address,enrollment_order,previous_education,absences,social_work"


def _students(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).order_by(Student.last_name, Student.first_name).all()


def _xml(content: bytes) -> tuple[ET.Element, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        xml = archive.read("word/document.xml").decode("utf-8")
    return ET.fromstring(xml), xml


def _paragraphs(content: bytes) -> list[str]:
    root, _ = _xml(content)
    return ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p")]


def _text(element) -> str:
    return "".join(x.text or "" for x in element.iter(f"{W}t"))


def _fill(client, headers, student, **payload):
    r = client.put(f"/students/{student.id}/dossier/profile", headers=headers, json=payload)
    assert r.status_code == 200, r.text


def _card(client, headers, student, fields, extra=""):
    return client.get(f"/students/{student.id}/dossier/card?fields={fields}{extra}", headers=headers)


def _mark(client, headers, group, student, code, day):
    r = client.post(f"/curator/groups/{group.id}/day/submit?date={day}", headers=headers, json={
        "exceptions": [{"student_id": student.id, "mark_code": code, "comment": None, "basis_reference": None}]})
    assert r.status_code == 200, r.text


def _absence_rows(content: bytes) -> list[list[str]]:
    root, _ = _xml(content)
    table = next(t for t in root.iter(f"{W}tbl") if _text(t).startswith("Причины"))
    return [[_text(c) for c in tr.findall(f"{W}tc")] for tr in table.findall(f"{W}tr")]


def test_selected_fields_are_filled_and_examples_are_gone(client, curator_headers, curator_group, db):
    s = _students(db, curator_group)[0]
    _fill(client, curator_headers, s, gender="female", birth_date="2008-05-17", birth_place="г. Тестоград",
          registration_address="ул. Тестовая, 1", enrollment_order="№ 5 от 25.08.2025",
          previous_education="11 классов, 2025 год, школа 1", additional_education="Футбол, шахматы")
    r = _card(client, curator_headers, s, ALL_FIELDS)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = _paragraphs(r.content)
    assert f"Обучающийся {s.full_name}" in text and f"1. (ФИО) {s.full_name}" in text
    assert f"Зачислен на ____ курс в группу {curator_group.code}" in text
    assert "3. Год, месяц и число рождения 17.05.2008" in text
    assert "4. Место рождения: г. Тестоград" in text and "5. Адрес регистрации: ул. Тестовая, 1" in text
    assert "Приказ № 5 от 25.08.2025" in text
    assert "11 классов, 2025 год, школа 1" in text and "1. Футбол, шахматы" in text
    root, xml = _xml(r.content)
    gender_p = next(p for p in root.iter(f"{W}p") if _text(p).startswith("2. Пол"))
    underlined = {_text(run) for run in gender_p.iter(f"{W}r") if run.find(f"{W}rPr/{W}u") is not None}
    assert underlined == {"женский"}  # пол показан подчёркиванием нужного слова
    assert "пример" not in xml and "ГБОУ СОШ" not in xml and "Ленина" not in xml  # примеры образца убраны


def test_unselected_fields_stay_blank_lines_even_if_the_dossier_has_data(client, curator_headers, curator_group, db):
    s = _students(db, curator_group)[0]
    _fill(client, curator_headers, s, birth_date="2008-05-17", birth_place="г. Тестоград", registration_address="ул. Тестовая, 1")
    text = _paragraphs(_card(client, curator_headers, s, "full_name").content)
    assert not any("17.05.2008" in p or "Тестоград" in p or "Тестовая" in p for p in text)
    assert any(p.startswith("3. Год, месяц и число рождения _") for p in text)
    assert any(p.startswith("4. Место рождения: ____") for p in text)
    assert "2. Пол: женский, мужской (подчеркнуть)" in text
    assert any(p.startswith("по специальности ____") for p in text) and "Дата зачисления: ____.____.________" in text


def test_absences_by_semester_come_from_the_journal(client, curator_headers, curator_group, db, today):
    s = _students(db, curator_group)[0]
    days = calendar_service.study_days_between(db, today - datetime.timedelta(days=21), today,
                                               study_group_id=curator_group.id, course=curator_group.course)
    _mark(client, curator_headers, curator_group, s, "н", days[-1])
    _mark(client, curator_headers, curator_group, s, "б", days[-2])
    rows = _absence_rows(_card(client, curator_headers, s, "full_name,absences").content)
    sem = svc.semester_of(days[-1], svc.first_study_year(curator_group, today_local()))
    assert 1 <= sem <= 10
    excused, unexcused = rows[2], rows[3]
    assert excused[0] == "По уважительной причине" and unexcused[0] == "По неуважительной причине"
    assert unexcused[sem] == "1" and excused[sem] == "1"  # день «н» и день «б» в одном семестре
    assert unexcused[-1] == "1" and excused[-1] == "1"  # «Всего»


def test_semester_without_submitted_days_stays_empty(client, curator_headers, curator_group, db):
    s = _students(db, curator_group)[0]
    rows = _absence_rows(_card(client, curator_headers, s, "absences").content)
    for row in rows[2:]:
        assert all(cell == "" for cell in row[1:])


def test_semester_numbering():
    f = svc.semester_of
    dates = [datetime.date(2026, 9, 1), datetime.date(2027, 1, 31), datetime.date(2027, 2, 1),
             datetime.date(2027, 8, 31), datetime.date(2027, 9, 1), datetime.date(2028, 1, 15)]
    assert [f(d, 2026) for d in dates] == [1, 1, 2, 2, 3, 3]
    group = StudyGroup(code="Т1", course=2, department_id=1)
    assert svc.first_study_year(group, datetime.date(2026, 10, 6)) == 2025  # 2 курс осенью 2026 — начали в 2025
    assert svc.first_study_year(group, datetime.date(2027, 3, 1)) == 2025  # весной — тот же учебный год


def test_blank_sections_can_be_dropped(client, curator_headers, curator_group, db):
    s = _students(db, curator_group)[0]
    full = _paragraphs(_card(client, curator_headers, s, "full_name").content)
    short = _paragraphs(_card(client, curator_headers, s, "full_name", "&blank_sections=false").content)
    assert any(p.startswith("II. Оценки") for p in full) and any(p.startswith("VIII. Взыскания") for p in full)
    assert not any(p.startswith(("II. ", "III. ", "IV. ", "V. ", "VI. ", "VII. ", "VIII. ")) for p in short)
    assert any(p.startswith("1. (ФИО)") for p in short)  # общие сведения остаются
    with_absences = _paragraphs(_card(client, curator_headers, s, "absences", "&blank_sections=false").content)
    assert any(p.startswith("IV. Число пропущенных") for p in with_absences)
    assert not any(p.startswith("II. ") for p in with_absences)


def test_group_document_has_a_card_per_student_with_page_breaks(client, curator_headers, curator_group, db):
    students = _students(db, curator_group)
    r = client.get(f"/curator/groups/{curator_group.id}/cards?fields=full_name,group&blank_sections=false", headers=curator_headers)
    assert r.status_code == 200
    _, xml = _xml(r.content)
    text = _paragraphs(r.content)
    assert [p for p in text if p.startswith("Обучающийся ")] == [f"Обучающийся {s.full_name}" for s in students]
    assert xml.count('w:type="page"') == len(students) - 1
    ids = re.findall(r'w14:paraId="([0-9A-F]+)"', xml)
    assert len(ids) == len(set(ids))
    assert "%D0%9B%D0%B8%D1%87%D0%BD%D1%8B%D0%B5_" in r.headers["content-disposition"]


def test_validation_and_access(client, curator_headers, admin_headers, curator_group, db):
    s = _students(db, curator_group)[0]
    other_group = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    other = db.query(Student).filter_by(study_group_id=other_group.id).first()
    for bad in ("", ",", "special", "full_name,health"):
        assert _card(client, curator_headers, s, bad).status_code == 400, bad
    assert client.get(f"/students/{s.id}/dossier/card", headers=curator_headers).status_code == 422  # поля обязательны
    assert client.get(f"/students/{s.id}/dossier/card?fields=full_name").status_code == 401
    assert _card(client, curator_headers, other, "full_name").status_code == 403
    assert _card(client, admin_headers, other, "full_name").status_code == 200
    assert client.get(f"/curator/groups/{other_group.id}/cards?fields=full_name", headers=curator_headers).status_code == 403
    assert client.get(f"/curator/groups/{other_group.id}/cards?fields=full_name", headers=admin_headers).status_code == 200
    assert client.get("/curator/groups/999999/cards?fields=full_name", headers=admin_headers).status_code == 404


def test_special_data_never_reaches_the_card_and_export_is_audited(client, curator_headers, curator_user, curator_group, db):
    s = _students(db, curator_group)[0]
    _fill(client, curator_headers, s, special={"has_ovz": True, "scholarship": "соцвыплата-секрет", "health_note": "диагноз-секрет"})
    _, xml = _xml(_card(client, curator_headers, s, ALL_FIELDS).content)
    assert "секрет" not in xml
    assert db.query(AuditLog).filter_by(action="dossier.student_card", user_id=curator_user.id).count() == 1
    client.get(f"/curator/groups/{curator_group.id}/cards?fields=full_name", headers=curator_headers)
    assert db.query(AuditLog).filter_by(action="group.student_cards", user_id=curator_user.id).count() == 1


def test_new_profile_fields_roundtrip(client, curator_headers, curator_group, db):
    s = _students(db, curator_group)[0]
    _fill(client, curator_headers, s, birth_place="  г. Тестоград ", previous_education="11 классов", enrollment_order="№ 5")
    profile = client.get(f"/students/{s.id}/dossier", headers=curator_headers).json()["profile"]
    assert (profile["birth_place"], profile["previous_education"], profile["enrollment_order"]) == ("г. Тестоград", "11 классов", "№ 5")
    too_long = client.put(f"/students/{s.id}/dossier/profile", headers=curator_headers, json={"birth_place": "я" * 256})
    assert too_long.status_code == 422


def test_frontend_field_list_matches_the_server():
    """Ключи и подписи в окне выбора (frontend/src/constants/studentCardFields.ts) — те же, что на сервере."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants" / "studentCardFields.ts").read_text(encoding="utf-8")
    block = source.split("export const STUDENT_CARD_FIELDS")[1].split("export const STUDENT_CARD_PRESETS")[0]
    assert re.findall(r'key: "([a-z_]+)", label: "([^"]+)"', block) == [(f.key, f.title) for f in svc.FIELDS]
