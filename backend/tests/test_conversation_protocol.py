"""«Протокол беседы» в Word из заметки журнала индивидуальной работы: выдуманные данные."""
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from app.models import AuditLog, Student, StudyGroup

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _student(db, group):
    return db.query(Student).filter_by(study_group_id=group.id).order_by(Student.last_name, Student.first_name).first()


def _paragraphs(content: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        root = ET.fromstring(archive.read("word/document.xml"))
    return ["".join("\n" if e.tag == f"{W}br" else (e.text or "") for e in p.iter() if e.tag in (f"{W}t", f"{W}br"))
            for p in root.iter(f"{W}p")]


def _note(client, headers, student, **payload):
    r = client.post(f"/students/{student.id}/dossier/notes", headers=headers, json={"kind": "conversation", "text": "Обсудили пропуски", **payload})
    assert r.status_code == 201, r.text
    return r.json()


def _protocol(client, headers, student, note):
    return client.get(f"/students/{student.id}/dossier/notes/{note['id']}/protocol", headers=headers)


def test_protocol_is_filled_from_the_note(client, curator_headers, curator_user, curator_group, db):
    student = _student(db, curator_group)
    note = _note(client, curator_headers, student, text="Обсудили пропуски.\nДоговорились о справках.",
                 goal="Выяснить причины пропусков", participants="Иванова Мария, мать\nКуратор Тестовый, куратор",
                 result="Родитель будет контролировать посещаемость", occurred_on="2026-10-01")
    r = _protocol(client, curator_headers, student, note)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = _paragraphs(r.content)
    assert "ПРОТОКОЛ БЕСЕДЫ" in text and "с родителями (законными представителями)" in text  # в присутствующих — мать
    assert "«01» октября 2026 г." in text
    assert student.full_name in text and curator_group.code in text
    assert "1. Иванова Мария, мать" in text and "2. Куратор Тестовый, куратор" in text
    assert "Цель беседы" in text and "Выяснить причины пропусков" in text
    assert "Тема обсуждения" in text and "Обсудили пропуски." in text and "Договорились о справках." in text
    assert "Родитель будет контролировать посещаемость" in text
    # форма нового протокола внизу: решение, заявления, подписи, ознакомление представителей
    for label in ("Решение", "Протокол прочитан", "Заявления, замечания", "Участники встречи:",
                  "Законные представители ознакомлены:", "(подпись)", "(ФИО)"):
        assert label in text
    assert text.index("Цель беседы") < text.index("Тема обсуждения") < text.index("Решение") < text.index("Участники встречи:")


def test_unfilled_parts_stay_blank_lines_and_subtitle_depends_on_whom(client, curator_headers, curator_group, db):
    student = _student(db, curator_group)
    note = _note(client, curator_headers, student)
    text = _paragraphs(_protocol(client, curator_headers, student, note).content)
    assert "с обучающимся" in text and "Цель беседы" in text and "Тема обсуждения" in text
    assert not any(p.startswith("1.") for p in text)  # присутствующих нет — остаются пустые линии
    parents = _note(client, curator_headers, student, kind="parent_invited")
    assert "с родителями (законными представителями)" in _paragraphs(_protocol(client, curator_headers, student, parents).content)


def test_layout_is_fixed_regardless_of_data(client, curator_headers, curator_group, db):
    """Ширины колонок заданы в документе: длинный текст переносится внутри поля, а не меняет раскладку."""
    student = _student(db, curator_group)
    short = _note(client, curator_headers, student)
    long_ = _note(client, curator_headers, student, text="Слово" * 400, goal="я" * 400, result="x " * 200)
    grids = []
    for note in (short, long_):
        with zipfile.ZipFile(io.BytesIO(_protocol(client, curator_headers, student, note).content)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        assert xml.count('<w:tblLayout w:type="fixed"/>') == xml.count("<w:tbl>") >= 8
        grids.append(re.findall(r'<w:gridCol w:w="(\d+)"/>', xml))
    assert grids[0] == grids[1]


def test_special_characters_are_escaped(client, curator_headers, curator_group, db):
    student = _student(db, curator_group)
    note = _note(client, curator_headers, student, text='Сказал: "Я & <вернусь>"', goal="A & B")
    text = _paragraphs(_protocol(client, curator_headers, student, note).content)
    assert 'Сказал: "Я & <вернусь>"' in text and "A & B" in text


def test_only_conversation_like_notes_and_access_rules(client, curator_headers, admin_headers, curator_group, db):
    student = _student(db, curator_group)
    other = db.query(Student).filter(Student.study_group_id != curator_group.id).first()
    plain = _note(client, curator_headers, student, kind="incident")
    assert _protocol(client, curator_headers, student, plain).status_code == 400
    note = _note(client, curator_headers, student, kind="parent_invited")
    assert _protocol(client, curator_headers, student, note).status_code == 200
    assert client.get(f"/students/{student.id}/dossier/notes/{note['id']}/protocol").status_code == 401
    assert client.get(f"/students/{other.id}/dossier/notes/{note['id']}/protocol", headers=curator_headers).status_code == 403
    assert client.get(f"/students/{student.id}/dossier/notes/999999/protocol", headers=curator_headers).status_code == 404
    # заметка другого студента через чужой адрес не отдаётся
    assert client.get(f"/students/{other.id}/dossier/notes/{note['id']}/protocol", headers=admin_headers).status_code == 404


def test_new_fields_roundtrip_and_export_is_audited(client, curator_headers, curator_user, curator_group, db):
    student = _student(db, curator_group)
    note = _note(client, curator_headers, student, goal="  цель  ", participants="  ", result="итог")
    assert (note["goal"], note["participants"], note["result"]) == ("цель", None, "итог")
    too_long = client.post(f"/students/{student.id}/dossier/notes", headers=curator_headers,
                           json={"kind": "conversation", "text": "x", "goal": "я" * 501})
    assert too_long.status_code == 422
    r = _protocol(client, curator_headers, student, note)
    assert "filename*=UTF-8''%D0%9F%D1%80%D0%BE%D1%82%D0%BE%D0%BA%D0%BE%D0%BB_" in r.headers["content-disposition"]
    assert db.query(AuditLog).filter_by(action="dossier.note_protocol", user_id=curator_user.id).count() == 1
    shown = client.get(f"/students/{student.id}/dossier", headers=curator_headers).json()["notes"][0]
    assert shown["goal"] == "цель" and shown["result"] == "итог"
