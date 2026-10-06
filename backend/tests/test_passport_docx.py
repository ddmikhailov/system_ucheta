"""Социальный паспорт группы в Word по образцу колледжа: выдуманные данные."""
import datetime
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from app.core.config import get_settings
from app.models import AuditLog, DossierAccessLog, Student, StudyGroup
from app.services import passport_service, passport_sheet_service

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BLOCKS = [
    "Многодетные семьи", "Неполные семьи (потеря", "Неполные семьи (родители в разводе", "Неполные семьи (матери-одиночки",
    "Малообеспеченные семьи", "Неблагополучные семьи", "Студенты-инвалиды", "Студенты , находящиеся под опекой",
    "Дети из семей родителей- инвалидов",
]


def _group_students(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.last_name, Student.first_name).all()


def _fill(client, headers, student, **payload):
    r = client.put(f"/students/{student.id}/dossier/profile", headers=headers, json=payload)
    assert r.status_code == 200, r.text


def _parse(content: bytes) -> tuple[ET.Element, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        xml = archive.read("word/document.xml").decode("utf-8")
    return ET.fromstring(xml), xml


def _cell_text(tc) -> str:
    return "".join("\n" if e.tag == f"{W}br" else (e.text or "") for e in tc.iter() if e.tag in (f"{W}t", f"{W}br"))


def _table(root) -> list[dict]:
    """Строки таблицы: подпись направления берётся с последней «открывающей» строки (объединённая ячейка)."""
    rows, label = [], None
    for tr in root.iter(f"{W}tr"):
        cells = tr.findall(f"{W}tc")
        merge = cells[0].find(f"{W}tcPr/{W}vMerge")
        if merge is not None and merge.get(f"{W}val") == "restart":
            label = " ".join(_cell_text(cells[0]).split())
        rows.append({"label": label, "cells": [_cell_text(c) for c in cells], "merge": merge})
    return rows[1:]  # без шапки таблицы


def _block(rows, title):
    return [r["cells"] for r in rows if r["label"] and r["label"].replace(" ,", ",").startswith(title.replace(" ,", ","))]


def _download(client, headers, group):
    r = client.get(f"/passport/group/{group.id}/docx", headers=headers)
    assert r.status_code == 200, r.text
    return r


def test_students_land_in_their_directions_with_contacts(client, curator_headers, curator_group, db):
    a, b, c, d = _group_students(db, curator_group)[:4]
    _fill(client, curator_headers, a, birth_date="2008-05-17", phone="+7 900 111-22-33",
          residence_address="г. Москва, ул. Тестовая, 1", special={"large_family": True, "low_income": True})
    client.post(f"/students/{a.id}/dossier/guardians", headers=curator_headers, json={"full_name": "Иванова Мария", "relation": "мать"})
    client.post(f"/students/{a.id}/dossier/guardians", headers=curator_headers, json={"full_name": "Иванов Пётр", "relation": "отец", "is_primary": True})
    _fill(client, curator_headers, b, special={"incomplete_family": "divorce", "is_orphan": True})
    _fill(client, curator_headers, c, special={"has_ovz": True, "pdn_kdn": True, "internal_record": True,
                                               "scholarship": "соц.", "health_note": "секрет"})
    _fill(client, curator_headers, d, special={"dysfunctional_family": True, "parent_disabled": True, "disability_group": "3"})

    root, xml = _parse(_download(client, curator_headers, curator_group).content)
    rows = _table(root)

    large = _block(rows, BLOCKS[0])
    assert large[0][1] == a.full_name and large[0][2] == "17.05.2008"
    assert large[0][3] == "Иванов Пётр (отец)\nИванова Мария (мать)"  # основной представитель первым
    assert large[0][4] == "г. Москва, ул. Тестовая, 1\n+7 900 111-22-33"
    assert [r[1] for r in _block(rows, BLOCKS[4])][0] == a.full_name  # два признака — две строки паспорта
    assert [r[1] for r in _block(rows, BLOCKS[2])][0] == b.full_name
    assert [r[1] for r in _block(rows, BLOCKS[7])][0] == b.full_name  # сирота — к опекаемым (отдельной строки в образце нет)
    for index in (5, 6, 8):
        assert [r[1] for r in _block(rows, BLOCKS[index])][0] == d.full_name
    # ОВЗ, учёт, стипендия и здоровье в документ не попадают совсем
    assert c.full_name not in xml and "секрет" not in xml and "соц." not in xml


def test_header_group_year_and_empty_directions_keep_blank_rows(client, curator_headers, curator_group, db):
    root, xml = _parse(_download(client, curator_headers, curator_group).content)
    texts = [t.text for t in root.iter(f"{W}t")]
    assert f"УЧЕБНОЙ ГРУППЫ {curator_group.code}" in texts
    today = datetime.date.today()
    year = today.year if today.month >= 9 else today.year - 1
    assert f"за {year}-{year + 1} учебный год" in texts
    rows = _table(root)
    assert len(rows) == len(BLOCKS) * passport_sheet_service.MIN_ROWS  # пока никого нет — по две пустые строки
    assert all(not any(cell for cell in r["cells"][1:]) for r in rows)
    assert "Куратор" in " ".join(texts) and "подпись" in " ".join(texts)  # блок подписей образца сохранён


def test_rows_grow_with_students_and_ids_stay_unique(client, curator_headers, curator_group, db):
    students = _group_students(db, curator_group)
    for s in students:
        _fill(client, curator_headers, s, special={"large_family": True})
    root, xml = _parse(_download(client, curator_headers, curator_group).content)
    rows = _table(root)
    assert len(_block(rows, BLOCKS[0])) == len(students)
    assert len(rows) == len(students) + (len(BLOCKS) - 1) * passport_sheet_service.MIN_ROWS
    ids = re.findall(r'w14:paraId="([0-9A-F]+)"', xml)
    assert len(ids) == len(set(ids))  # копии строк образца без повторных идентификаторов
    # объединённая ячейка направления: одна «restart» на направление, остальные — продолжения
    assert sum(1 for r in rows if r["merge"] is not None and r["merge"].get(f"{W}val") == "restart") == len(BLOCKS)


def test_access_follows_the_passport_rules(client, curator_headers, admin_headers, curator_group, db):
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    assert client.get(f"/passport/group/{curator_group.id}/docx").status_code == 401
    assert client.get(f"/passport/group/{other.id}/docx", headers=curator_headers).status_code == 403
    assert client.get("/passport/group/999999/docx", headers=curator_headers).status_code == 404
    assert client.get(f"/passport/group/{other.id}/docx", headers=admin_headers).status_code == 200


def test_without_encryption_key_the_document_is_refused(client, curator_headers, curator_group, monkeypatch):
    monkeypatch.setattr(get_settings(), "dossier_encryption_key", "")
    r = client.get(f"/passport/group/{curator_group.id}/docx", headers=curator_headers)
    assert r.status_code == 409 and "ключ шифрования" in r.json()["detail"]


def test_export_is_logged_like_a_named_passport(client, curator_headers, curator_user, curator_group, db):
    a, b = _group_students(db, curator_group)[:2]
    _fill(client, curator_headers, a, special={"large_family": True})
    _fill(client, curator_headers, b, special={"large_family": True, "low_income": True})
    db.query(DossierAccessLog).delete()
    db.commit()
    r = _download(client, curator_headers, curator_group)
    assert "filename*=UTF-8''%D0%A1%D0%BE%D1%86%D0%B8%D0%B0%D0%BB%D1%8C%D0%BD%D1%8B%D0%B9_" in r.headers["content-disposition"]
    logged = {row.student_id for row in db.query(DossierAccessLog).filter_by(user_id=curator_user.id, included_special=True)}
    assert logged == {a.id, b.id}  # каждый студент один раз, даже если он в двух направлениях
    assert db.query(AuditLog).filter_by(action="passport.docx", user_id=curator_user.id).count() == 1


def test_new_family_fields_are_saved_validated_and_counted_on_screen(client, curator_headers, curator_group, db):
    a, b = _group_students(db, curator_group)[:2]
    _fill(client, curator_headers, a, special={"incomplete_family": "single_mother", "dysfunctional_family": True})
    _fill(client, curator_headers, b, special={"incomplete_family": "loss", "parent_disabled": True})
    bad = client.put(f"/students/{a.id}/dossier/profile", headers=curator_headers, json={"special": {"incomplete_family": "other"}})
    assert bad.status_code == 422
    dossier = client.get(f"/students/{a.id}/dossier", headers=curator_headers).json()
    assert dossier["special"]["incomplete_family"] == "single_mother" and dossier["special"]["dysfunctional_family"] is True

    data = client.get(f"/passport/group/{curator_group.id}", headers=curator_headers).json()
    by_key = {c["key"]: c for c in data["categories"]}
    assert by_key["incomplete_single_mother"]["names"] == [a.full_name]
    assert by_key["incomplete_loss"]["names"] == [b.full_name]
    assert by_key["dysfunctional"]["count"] == 1 and by_key["parent_disabled"]["count"] == 1
    assert by_key["incomplete_divorce"]["count"] == 0


def test_template_directions_match_the_screen_categories(client, curator_headers, curator_group, db):
    """Девять направлений образца — девять категорий на экране (плюс «Сироты» → к опекаемым, ОВЗ и учёт — только на экране)."""
    screen = {key for key, _, _ in passport_service.CATEGORIES}
    assert {"large_family", "incomplete_loss", "incomplete_divorce", "incomplete_single_mother", "low_income",
            "dysfunctional", "disability", "guardianship", "parent_disabled"} <= screen
    assert len(passport_sheet_service.DIRECTIONS) == 9
