"""«Лист ознакомления и письменного объяснения по пропускам и опозданиям» (.docx по образцу колледжа)."""
import datetime
import io
import re
import zipfile
from urllib.parse import unquote

import pytest

from app.core.time import today_local
from app.models import AuditLog, Student
from app.services import absence_sheet_service as svc
from app.services import calendar_service

D = datetime.date
ROWS = [
    svc.SheetRow(D(2026, 10, 1), "Неуважительная причина", False, False),
    svc.SheetRow(D(2026, 10, 2), "Опоздание", True, False),
    svc.SheetRow(D(2026, 10, 5), "Больничный лист", False, True),
    svc.SheetRow(D(2026, 10, 6), "Ушёл с занятий", False, False),
]


def _build(rows=ROWS, **over):
    kw = dict(student_name="Лебедева Елена Андреевна", group_code="СА172", department_name="Диджитал",
              curator_name="Иванова Анна Ивановна", date_from=D(2026, 10, 1), date_to=D(2026, 10, 7), rows=rows)
    kw.update(over)
    return svc.build_docx(**kw)


# Текстовый узел <w:t> или <w:t xml:space="preserve"> (но не <w:tc>, <w:tcPr>, <w:tbl>…).
_T = r"<w:t(?: [^>]*)?>(.*?)</w:t>"


def _doc_xml(data: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")


def _text(data: bytes) -> str:
    """Весь видимый текст документа подряд (абзацы разделены переводом строки)."""
    xml = _doc_xml(data)
    paragraphs = re.findall(r"<w:p>.*?</w:p>|<w:p .*?</w:p>", xml, flags=re.S)
    return "\n".join("".join(re.findall(_T, p, flags=re.S)) for p in paragraphs)


def _table_rows(data: bytes) -> list[list[str]]:
    """Строки таблицы дней (вторая таблица документа)."""
    xml = _doc_xml(data)
    tables = re.findall(r"<w:tbl>.*?</w:tbl>", xml, flags=re.S)
    rows = re.findall(r"<w:tr>.*?</w:tr>", tables[1], flags=re.S)
    return [["".join(re.findall(_T, c, flags=re.S)) for c in re.findall(r"<w:tc>.*?</w:tc>", r, flags=re.S)]
            for r in rows]


# ---------- сборка документа ----------

def test_document_is_filled_from_the_template_without_hours():
    data = _build()
    text = _text(data)
    assert "Заведующему учебным отделением «Диджитал»" in text
    assert "от обучающегося(ейся) группы СА172" in text
    assert text.count("Лебедева Елена Андреевна") == 2  # строка над «(Ф.И.О. обучающегося полностью)» и «Я, …»
    assert "Я, Лебедева Елена Андреевна, обучающийся(аяся) группы СА172, подтверждаю" in text
    assert "Период: с «01» октября 2026 г. по «07» октября 2026 г." in text
    assert "Куратор учебной группы: ____________________ / Иванова Анна Ивановна" in text
    # Часов в листе нет — ни в таблице, ни в итоговой строке.
    assert "часов" not in text.lower() and "ак. часов" not in text
    assert _table_rows(data)[0] == ["№", "Дата", "Пропуск / опоздание (отметка в журнале)"]


def test_table_lists_days_in_order_with_numbers():
    rows = _table_rows(_build())
    assert rows[1:] == [
        ["1", "01.10.2026", "Неуважительная причина"], ["2", "02.10.2026", "Опоздание"],
        ["3", "05.10.2026", "Больничный лист"], ["4", "06.10.2026", "Ушёл с занятий"],
    ]


def test_totals_line_counts_days_lates_and_truancy():
    # дни с пропусками: 1, 5, 6 октября (опоздание 2-го — не пропуск); прогулы — без уважительной причины: 1 и 6
    assert "Итого за указанный период: дней с пропусками 3; опозданий 1; прогулов 2." in _text(_build())
    t = svc.totals(ROWS)
    assert (t.days_with_absences, t.late, t.truancy) == (3, 1, 2)
    assert svc.totals([]) == svc.SheetTotals(0, 0, 0)


def test_static_texts_footer_and_page_setup_are_kept_exactly():
    """«Строго по образцу»: все части образца, кроме тела документа, байт в байт те же; постоянные тексты на месте."""
    out = zipfile.ZipFile(io.BytesIO(_build()))
    src = zipfile.ZipFile(svc.TEMPLATE_PATH)
    assert out.namelist() == src.namelist()
    for name in src.namelist():
        if name != "word/document.xml":
            assert out.read(name) == src.read(name), name
    new_xml, old_xml = out.read("word/document.xml").decode(), src.read("word/document.xml").decode()
    # Параметры страницы, подвал, шапка корня документа, подписи — без изменений.
    assert re.search(r"<w:sectPr.*</w:sectPr>", new_xml, flags=re.S).group(0) == re.search(r"<w:sectPr.*</w:sectPr>", old_xml, flags=re.S).group(0)
    assert new_xml[: new_xml.index("<w:body>")] == old_xml[: old_xml.index("<w:body>")]
    text = _text(_build())
    for fragment in (
        "ЛИСТ ОЗНАКОМЛЕНИЯ И ПИСЬМЕННОГО ОБЪЯСНЕНИЯ", "п. 1.5 — Правила обязательны", "более 3 прогулов в месяц",
        "п. 6.11 — за неисполнение и нарушение Устава", "согласен(на) / имею замечания (нужное подчеркнуть)",
        "Подтверждающие документы (при наличии)", "Подпись обучающегося", "Расшифровка подписи",
    ):
        assert fragment in text


def test_table_look_matches_the_template_table():
    xml = _doc_xml(_build())
    src = zipfile.ZipFile(svc.TEMPLATE_PATH).read("word/document.xml").decode()
    # Свойства таблицы (границы, выравнивание, фиксированная раскладка) — те же, что у таблицы образца.
    old_props = re.findall(r"<w:tbl><w:tblPr>.*?</w:tblPr>", src, flags=re.S)[1]
    new_props = re.findall(r"<w:tbl><w:tblPr>.*?</w:tblPr>", xml, flags=re.S)[1]
    assert new_props == old_props
    assert len(re.findall(r"<w:tbl>", xml)) == 3
    assert 'w:val="Times New Roman"' not in xml  # шрифт задан атрибутами w:ascii/w:hAnsi, как в образце
    assert xml.count('w:ascii="Times New Roman"') > 20


def test_special_characters_are_escaped():
    data = _build(student_name='Иванов & <Петров> "Сидоров"', curator_name="О'Брайен & Ко")
    zipfile.ZipFile(io.BytesIO(data)).testzip()
    import xml.dom.minidom
    xml.dom.minidom.parseString(_doc_xml(data))  # документ остался well-formed XML
    text = _text(data)
    assert "Иванов &amp; &lt;Петров&gt; \"Сидоров\"" in text and "О'Брайен &amp; Ко" in text


def test_missing_curator_leaves_a_blank_line():
    assert "Куратор учебной группы: ____________________ / ______________________________" in _text(_build(curator_name=None))


def test_many_days_make_many_rows_and_repeat_the_header():
    many = [svc.SheetRow(D(2026, 9, 1) + datetime.timedelta(days=i), "Неуважительная причина", False, False) for i in range(40)]
    data = _build(rows=many)
    assert len(_table_rows(data)) == 41 and _table_rows(data)[-1][0] == "40"
    assert "<w:tblHeader/>" in _doc_xml(data)


def test_changed_template_fails_loudly(tmp_path, monkeypatch):
    broken = tmp_path / "broken.docx"
    with zipfile.ZipFile(svc.TEMPLATE_PATH) as src, zipfile.ZipFile(broken, "w") as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename == "word/document.xml":
                payload = payload.replace("Заведующему учебным отделением".encode(), "Заведующему отделением".encode())
            dst.writestr(info, payload)
    monkeypatch.setattr(svc, "TEMPLATE_PATH", broken)
    with pytest.raises(svc.TemplateMismatch):
        _build()


def test_template_ships_with_the_release_build():
    import importlib.util
    from pathlib import Path
    tool_path = Path(__file__).resolve().parent.parent.parent / "tools" / "build_release.py"
    if not tool_path.is_file():
        pytest.skip("инструмента сборки нет вне репозитория")
    spec = importlib.util.spec_from_file_location("build_release", tool_path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert "backend/app/templates/absence_sheet.docx" in tool.select_files(["backend/app/templates/absence_sheet.docx"])


# ---------- отбор отметок ----------

def _mark(client, headers, group, student, code, day):
    r = client.post(f"/curator/groups/{group.id}/day/submit?date={day}", headers=headers, json={
        "exceptions": [{"student_id": student.id, "mark_code": code, "comment": None, "basis_reference": None}]})
    assert r.status_code == 200, r.text


def _study_days(db, group, today, n=8):
    days = calendar_service.study_days_between(db, today - datetime.timedelta(days=21), today, study_group_id=group.id, course=group.course)
    assert len(days) >= n
    return days[-n:]


def _first_student(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).first()


def test_collect_rows_filters_by_period_and_excuse(client, curator_headers, curator_group, imported, db, today):
    s = _first_student(db, curator_group)
    d = _study_days(db, curator_group, today)
    _mark(client, curator_headers, curator_group, s, "н", d[-1])
    _mark(client, curator_headers, curator_group, s, "о", d[-2])
    _mark(client, curator_headers, curator_group, s, "б", d[-3])
    _mark(client, curator_headers, curator_group, s, "у", d[-4])
    _mark(client, curator_headers, curator_group, s, "н", d[0])  # вне периода ниже

    default = svc.collect_rows(db, s, d[-4], d[-1])
    assert [(r.date, r.label, r.is_late) for r in default] == [
        (d[-4], "Ушёл с занятий", False), (d[-2], "Опоздание", True), (d[-1], "Неуважительная причина", False)]
    with_excused = svc.collect_rows(db, s, d[-4], d[-1], include_excused=True)
    assert [r.label for r in with_excused] == ["Ушёл с занятий", "Больничный лист", "Опоздание", "Неуважительная причина"]
    assert svc.totals(with_excused).truancy == 2 and svc.totals(with_excused).days_with_absences == 3
    assert svc.collect_rows(db, s, d[-4], d[-1])[0].date == d[-4]  # d[0] в период не попал


# ---------- API ----------

def _get(client, headers, sid, date_from, date_to, **params):
    q = "&".join(f"{k}={v}" for k, v in {"date_from": date_from, "date_to": date_to, **params}.items())
    return client.get(f"/students/{sid}/absence-sheet?{q}", headers=headers)


def test_curator_downloads_the_filled_sheet(client, curator_headers, curator_user, curator_group, imported, db, today):
    s = _first_student(db, curator_group)
    d = _study_days(db, curator_group, today)
    _mark(client, curator_headers, curator_group, s, "н", d[-1])
    _mark(client, curator_headers, curator_group, s, "о", d[-2])
    r = _get(client, curator_headers, s.id, d[-3], d[-1])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    disposition = r.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="absence_sheet.docx"')
    assert unquote(disposition.split("filename*=UTF-8''")[1]) == f"Лист_ознакомления_{s.last_name}_{curator_group.code}_{d[-3]:%d.%m.%Y}-{d[-1]:%d.%m.%Y}.docx"
    text = _text(r.content)
    assert s.full_name in text and curator_group.code in text and curator_group.department.name in text
    assert f"Период: с «{d[-3].day:02d}» " in text and "Итого за указанный период: дней с пропусками 1; опозданий 1; прогулов 1." in text
    assert curator_user.full_name in text  # куратор группы — в подписи
    assert [row[1:] for row in _table_rows(r.content)[1:]] == [
        [d[-2].strftime("%d.%m.%Y"), "Опоздание"], [d[-1].strftime("%d.%m.%Y"), "Неуважительная причина"]]
    log = db.query(AuditLog).filter(AuditLog.action == "student.absence_sheet").one()
    assert log.entity_id == str(s.id) and log.new_value == f"{d[-3]}..{d[-1]}"


def test_excused_absences_only_with_the_flag(client, curator_headers, curator_group, imported, db, today):
    s = _first_student(db, curator_group)
    d = _study_days(db, curator_group, today)
    _mark(client, curator_headers, curator_group, s, "б", d[-1])
    assert _get(client, curator_headers, s.id, d[-2], d[-1]).status_code == 400
    r = _get(client, curator_headers, s.id, d[-2], d[-1], include_excused="true")
    assert r.status_code == 200 and "Больничный лист" in _text(r.content)


def test_validation_errors(client, curator_headers, curator_group, imported, db, today):
    s = _first_student(db, curator_group)
    d = _study_days(db, curator_group, today)
    _mark(client, curator_headers, curator_group, s, "н", d[-1])
    empty = _get(client, curator_headers, s.id, d[0], d[1])
    assert empty.status_code == 400 and "нет пропусков и опозданий" in empty.json()["detail"]
    future = _get(client, curator_headers, s.id, today_local(), today_local() + datetime.timedelta(days=1))
    assert future.status_code == 400 and "в будущее" in future.json()["detail"]
    reversed_ = _get(client, curator_headers, s.id, d[-1], d[-2])
    assert reversed_.status_code == 400
    too_long = _get(client, curator_headers, s.id, today_local() - datetime.timedelta(days=400), today_local())
    assert too_long.status_code == 400 and "366" in too_long.json()["detail"]
    assert client.get(f"/students/{s.id}/absence-sheet", headers=curator_headers).status_code == 422  # даты обязательны


def test_access_follows_student_access(client, curator_group, curator_headers, db_second_curator, admin_headers, imported, db, today):
    from tests.conftest import _login
    s = _first_student(db, curator_group)
    d = _study_days(db, curator_group, today)
    _mark(client, curator_headers, curator_group, s, "н", d[-1])
    other = _login(client, db_second_curator.username, "SecondCurator123!")
    assert _get(client, other, s.id, d[-2], d[-1]).status_code == 403
    assert _get(client, admin_headers, s.id, d[-2], d[-1]).status_code == 200
    assert _get(client, admin_headers, 999999, d[-2], d[-1]).status_code == 404
    assert client.get(f"/students/{s.id}/absence-sheet?date_from={d[-2]}&date_to={d[-1]}").status_code == 401
