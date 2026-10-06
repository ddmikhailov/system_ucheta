"""«Протокол беседы» в Word из заметки журнала индивидуальной работы: выдуманные данные."""
import io
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
    assert "«01» октября 2026 г." in text
    assert f"ФИО обучающегося {student.full_name}" in text and f"Группа {curator_group.code}" in text
    assert "1. Иванова Мария, мать" in text and "2. Куратор Тестовый, куратор" in text
    assert "1…(ФИО, должность/статус)" not in text  # образцовые строки заменены списком
    assert "Цель беседы: Выяснить причины пропусков" in text
    assert "Содержание беседы: Обсудили пропуски.\nДоговорились о справках." in text
    assert any(p.endswith("Результат беседы: Родитель будет контролировать посещаемость") for p in text)
    assert any("подпись куратора учебной группы" in p for p in text)  # места для подписей остались из образца


def test_unfilled_parts_stay_blank_lines_for_handwriting(client, curator_headers, curator_group, db):
    student = _student(db, curator_group)
    note = _note(client, curator_headers, student)
    text = _paragraphs(_protocol(client, curator_headers, student, note).content)
    assert "1…(ФИО, должность/статус)" in text and "2…" in text
    assert any(p.startswith("Цель беседы: ___") for p in text)
    assert any(p.endswith("Результат беседы: " + "_" * 49) for p in text)  # итог не задан — черта образца


def test_special_characters_are_escaped(client, curator_headers, curator_group, db):
    student = _student(db, curator_group)
    note = _note(client, curator_headers, student, text='Сказал: "Я & <вернусь>"', goal="A & B")
    text = _paragraphs(_protocol(client, curator_headers, student, note).content)
    assert 'Содержание беседы: Сказал: "Я & <вернусь>"' in text and "Цель беседы: A & B" in text


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
