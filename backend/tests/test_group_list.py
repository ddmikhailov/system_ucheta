"""«Список группы» для печати (.docx) с настраиваемыми столбцами: выдуманные данные."""
import datetime
import io
import xml.etree.ElementTree as ET
import zipfile

import pytest
from sqlalchemy import event

from app.models import AuditLog, Student, StudentGuardian, StudentProfile, StudyGroup
from app.services import group_list_service

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse(content: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        for name in ("[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"):
            ET.fromstring(archive.read(name))  # каждая часть — корректный XML
        return ET.fromstring(archive.read("word/document.xml"))


def table_rows(root: ET.Element) -> list[list[str]]:
    rows = []
    for tr in root.iter(f"{W}tr"):
        row = []
        for tc in tr.iter(f"{W}tc"):
            row.append("".join(t.text or "" if t.tag == f"{W}t" else "\n" for t in tc.iter() if t.tag in (f"{W}t", f"{W}br")))
        rows.append(row)
    return rows


def url(group_id, fields, extra=""):
    return f"/curator/groups/{group_id}/roster-sheet?fields={fields}{extra}"


@pytest.fixture()
def group_with_contacts(db, curator_group):
    students = db.query(Student).filter_by(study_group_id=curator_group.id).order_by(Student.last_name, Student.first_name).all()
    first, second = students[0], students[1]
    db.add(StudentProfile(student_id=first.id, phone="+7 900 111-22-33", email="a@example.test", birth_date=datetime.date(2008, 5, 17),
                          funding="budget", registration_address="г. Москва, ул. Тестовая, 1"))
    db.add(StudentGuardian(student_id=first.id, full_name="Иванова Мария", relation="мать", phone="+7 911 000-00-01", is_primary=True))
    db.add(StudentGuardian(student_id=first.id, full_name="Иванов Пётр", relation="отец", phone=None))
    db.add(StudentProfile(student_id=second.id, phone="+7 900 444-55-66"))
    db.commit()
    return curator_group, first, second


def test_name_phone_email_gives_a_three_column_table(client, curator_headers, group_with_contacts):
    group, first, second = group_with_contacts
    r = client.get(url(group.id, "full_name,phone,email", "&numbering=false"), headers=curator_headers)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    rows = table_rows(parse(r.content))
    assert rows[0] == ["ФИО", "Телефон", "E-mail"]  # ровно три столбца
    assert rows[1] == [first.full_name, "+7 900 111-22-33", "a@example.test"]
    assert rows[2] == [second.full_name, "+7 900 444-55-66", ""]  # чего нет в досье — пустая ячейка
    assert len(rows) == 1 + db_count(client, curator_headers, group.id)


def db_count(client, headers, group_id):
    return len(client.get(f"/curator/groups/{group_id}/day?date={datetime.date.today()}", headers=headers).json()["entries"])


def test_numbering_adds_a_numbered_first_column(client, curator_headers, group_with_contacts):
    group, first, _ = group_with_contacts
    rows = table_rows(parse(client.get(url(group.id, "full_name,phone"), headers=curator_headers).content))
    assert rows[0] == ["№", "ФИО", "Телефон"]
    assert rows[1][:2] == ["1", first.full_name] and rows[2][0] == "2"


def test_columns_keep_the_chosen_order_and_ignore_repeats(client, curator_headers, group_with_contacts):
    group, *_ = group_with_contacts
    rows = table_rows(parse(client.get(url(group.id, "phone,full_name,phone", "&numbering=false"), headers=curator_headers).content))
    assert rows[0] == ["Телефон", "ФИО"]


def test_guardians_are_listed_one_per_line_and_blank_columns_are_empty(client, curator_headers, group_with_contacts):
    group, first, _ = group_with_contacts
    rows = table_rows(parse(client.get(url(group.id, "full_name,guardians,guardian_phones,funding,birth_date,signature", "&numbering=false"), headers=curator_headers).content))
    assert rows[0] == ["ФИО", "Представители", "Телефоны представителей", "Бюджет / договор", "Дата рождения", "Подпись"]
    assert rows[1][1] == "Иванова Мария (мать)\nИванов Пётр (отец)"  # основной представитель первым
    assert rows[1][2] == "+7 911 000-00-01\n—"
    assert rows[1][3:] == ["Бюджет", "17.05.2008", ""]


def test_page_orientation_and_title(client, curator_headers, group_with_contacts):
    group, *_ = group_with_contacts
    narrow = parse(client.get(url(group.id, "full_name,phone,email"), headers=curator_headers).content)
    wide = parse(client.get(url(group.id, "full_name,phone,email,messenger,birth_date"), headers=curator_headers).content)
    assert narrow.find(f".//{W}pgSz").get(f"{W}orient") is None
    assert wide.find(f".//{W}pgSz").get(f"{W}orient") == "landscape"

    custom = parse(client.get(url(group.id, "full_name", "&title=Список для экскурсии"), headers=curator_headers).content)
    texts = [t.text for t in custom.iter(f"{W}t")]
    assert "Список для экскурсии" in texts and f"Список группы {group.code}" not in texts
    default = [t.text for t in parse(client.get(url(group.id, "full_name"), headers=curator_headers).content).iter(f"{W}t")]
    assert f"Список группы {group.code}" in default


def test_table_header_repeats_and_widths_fill_the_page(client, curator_headers, group_with_contacts):
    group, *_ = group_with_contacts
    root = parse(client.get(url(group.id, "full_name,phone,email"), headers=curator_headers).content)
    assert root.find(f".//{W}tblHeader") is not None
    grid = [int(c.get(f"{W}w")) for c in root.iter(f"{W}gridCol")]
    page = root.find(f".//{W}pgSz")
    margins = root.find(f".//{W}pgMar")
    assert sum(grid) == int(page.get(f"{W}w")) - int(margins.get(f"{W}left")) - int(margins.get(f"{W}right"))


def test_special_data_cannot_be_requested(client, curator_headers, group_with_contacts):
    group, *_ = group_with_contacts
    for key in ("special", "health", "ovz", "orphan", "special_enc"):
        r = client.get(url(group.id, f"full_name,{key}"), headers=curator_headers)
        assert r.status_code == 400 and "Неизвестные столбцы" in r.json()["detail"]
    assert {f.key for f in group_list_service.FIELDS}.isdisjoint({"special", "health", "ovz", "orphan", "special_enc"})


def test_empty_or_unknown_selection_is_rejected(client, curator_headers, group_with_contacts):
    group, *_ = group_with_contacts
    assert client.get(url(group.id, ","), headers=curator_headers).status_code == 400
    assert client.get(url(group.id, "nonsense"), headers=curator_headers).status_code == 400
    assert client.get(f"/curator/groups/{group.id}/roster-sheet", headers=curator_headers).status_code == 422  # fields обязателен
    assert client.get(url(group.id, "full_name", "&title=" + "я" * 121), headers=curator_headers).status_code == 422


def test_access_follows_the_journal_rules(client, curator_headers, admin_headers, group_with_contacts, db):
    group, *_ = group_with_contacts
    other = db.query(StudyGroup).filter(StudyGroup.id != group.id).first()
    assert client.get(url(group.id, "full_name")).status_code == 401
    assert client.get(url(other.id, "full_name"), headers=curator_headers).status_code == 403  # чужая группа
    assert client.get(url(group.id, "full_name"), headers=admin_headers).status_code == 200  # администрация — любая
    assert client.get(url(999999, "full_name"), headers=admin_headers).status_code == 404


def test_names_with_xml_special_characters_do_not_break_the_document(client, curator_headers, group_with_contacts, db):
    group, first, _ = group_with_contacts
    first.last_name = 'Тестов & <Ко> "Ж"'
    db.query(StudentProfile).filter_by(student_id=first.id).one().email = "x\x0b@example.test"
    db.commit()
    rows = table_rows(parse(client.get(url(group.id, "full_name,email"), headers=curator_headers).content))
    assert any('Тестов & <Ко> "Ж"' in row[1] for row in rows)
    assert any("x@example.test" in row[2] for row in rows)  # управляющий символ убран


def test_generation_is_logged_and_filename_is_readable(client, curator_headers, curator_user, group_with_contacts, db):
    group, *_ = group_with_contacts
    r = client.get(url(group.id, "full_name,phone"), headers=curator_headers)
    assert "filename*=UTF-8''%D0%A1%D0%BF%D0%B8%D1%81%D0%BE%D0%BA_" in r.headers["content-disposition"]
    entry = db.query(AuditLog).filter_by(action="group.roster_sheet").one()
    assert (entry.user_id, entry.entity_id, entry.new_value) == (curator_user.id, str(group.id), "full_name,phone")


def test_number_of_queries_does_not_grow_with_the_group(client, curator_headers, group_with_contacts, db):
    group, *_ = group_with_contacts
    counter = {"n": 0}

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        client.get(url(group.id, "full_name,phone,email,guardians,guardian_phones,funding"), headers=curator_headers)
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    assert counter["n"] <= 25, counter["n"]  # вход, права, группа, студенты, досье, представители, журнал — не по запросу на студента


def test_frontend_field_list_matches_the_server():
    """Ключи и подписи столбцов в окне выбора (frontend/src/constants/groupListFields.ts) — те же, что на сервере."""
    import pathlib
    import re

    source = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants" / "groupListFields.ts").read_text(encoding="utf-8")
    fields_block = source.split("export const GROUP_LIST_FIELDS")[1].split("export const GROUP_LIST_PRESETS")[0]
    front = re.findall(r'key: "([a-z_]+)", label: "([^"]+)"', fields_block)
    assert front == [(f.key, f.title) for f in group_list_service.FIELDS]
    presets = source.split("export const GROUP_LIST_PRESETS")[1]
    used = set(re.findall(r'"([a-z_]+)"', presets.split("keys:", 1)[1] if "keys:" in presets else ""))
    assert used <= {f.key for f in group_list_service.FIELDS}
