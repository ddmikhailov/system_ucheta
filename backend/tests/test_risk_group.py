"""Посещаемость с начала семестра и два статуса по ней (решение 21.10.2026):

  * «Группа риска» — пропусков без уважительной причины («н», «у») больше 40 % сданных дней;
  * «Восполнить пропуски» — не в группе риска, но без практики и ИУП посещаемость ниже 85 %; куратор закрывает
    комментарием, снова студент появляется после трёх новых таких пропусков."""
import datetime

import pytest

from app.api.routers import curator as curator_router
from app.core.config import get_settings
from app.models import AbsenceCompensation, AuditLog, MarkCode, Student
from app.services import attendance_service, calendar_service, individual_work_service, stats_service

START = datetime.date(2026, 9, 21)


def _days(db, group, n):
    days = calendar_service.study_days_between(db, START, START + datetime.timedelta(days=60), study_group_id=group.id, course=group.course)
    assert len(days) >= n
    return days[:n]


def _submit(db, group, user, day, marks=None):
    exceptions = [{"student_id": sid, "mark_code": code, "comment": None, "basis_reference": None} for sid, code in (marks or {}).items()]
    attendance_service.submit_day(db, group.id, day, exceptions, user, today=day)


def _students(db, group, day):
    return attendance_service.get_active_students(db, group.id, day)


def _rates(db, group, day):
    students = _students(db, group, day)
    return students, attendance_service.attendance_rates_bulk(db, students, day)


def _fill(db, group, user, days, plan):
    """plan: {student_id: [код на день 0, код на день 1, …]} — None или конец списка = присутствовал."""
    for i, day in enumerate(days):
        marks = {sid: codes[i] for sid, codes in plan.items() if i < len(codes) and codes[i]}
        _submit(db, group, user, day, marks)


def test_percent_counts_all_absences_but_not_lateness(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3, s4 = _students(db, curator_group, days[0])[:4]
    _fill(db, curator_group, curator_user, days, {
        s1.id: ["н", "н"],              # 80 %, оба без причины
        s2.id: [None, None, "н", "б"],  # больничный — тоже пропуск: 80 %
        s3.id: ["о"] * 5,               # опоздания — присутствие
    })
    _, rates = _rates(db, curator_group, days[-1])
    assert (rates[s1.id].days, rates[s1.id].absent, rates[s1.id].percent) == (10, 2, 80.0)
    assert (rates[s1.id].absent_unexcused, rates[s1.id].unexcused_percent) == (2, 20.0)
    assert (rates[s2.id].percent, rates[s2.id].absent_unexcused, rates[s2.id].absent_to_compensate) == (80.0, 1, 2)
    assert rates[s3.id].percent == 100.0 and rates[s4.id].percent == 100.0
    # 20 % пропусков без причины — ещё не риск, но учебный процесс пропущен: восполнить
    assert not rates[s1.id].is_risk and rates[s1.id].needs_compensation
    assert not rates[s2.id].is_risk and rates[s2.id].needs_compensation
    assert not rates[s3.id].needs_compensation and not rates[s4.id].needs_compensation


def test_risk_is_strictly_more_than_40_percent_unexcused(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3 = _students(db, curator_group, days[0])[:3]
    _fill(db, curator_group, curator_user, days, {
        s1.id: ["н"] * 4,              # ровно 40 % без причины (посещаемость 60 %) → ещё не риск
        s2.id: ["н"] * 4 + ["у"],      # 50 %: «ушёл с занятий» — тоже без причины → риск
        s3.id: ["б"] * 8,              # 20 % посещаемости, но всё по больничному → не риск
    })
    _, rates = _rates(db, curator_group, days[-1])
    assert rates[s1.id].percent == 60.0 and not rates[s1.id].is_risk and rates[s1.id].needs_compensation
    assert rates[s2.id].unexcused_percent == 50.0 and rates[s2.id].is_risk
    assert not rates[s2.id].needs_compensation  # группа риска важнее: там индивидуальная работа
    assert rates[s3.id].percent == 20.0 and not rates[s3.id].is_risk and rates[s3.id].needs_compensation
    assert get_settings().risk_unexcused_percent == 40.0 and get_settings().risk_attendance_percent == 85.0


def test_practice_and_individual_plan_need_no_compensation(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3 = _students(db, curator_group, days[0])[:3]
    _fill(db, curator_group, curator_user, days, {
        s1.id: ["р"] * 6,              # практика: отсутствие (40 %), но восполнять нечего
        s2.id: ["и"] * 3 + ["б"],      # ИУП + один больничный: без ИУП 90 % → не нужно
        s3.id: ["р"] * 3 + ["б"] * 2,  # практика + два больничных: без практики 80 % → нужно
    })
    _, rates = _rates(db, curator_group, days[-1])
    assert rates[s1.id].percent == 40.0 and rates[s1.id].absent_to_compensate == 0
    assert not rates[s1.id].is_risk and not rates[s1.id].needs_compensation
    assert rates[s2.id].percent == 60.0 and not rates[s2.id].needs_compensation
    assert rates[s3.id].percent == 50.0 and rates[s3.id].absent_to_compensate == 2 and rates[s3.id].needs_compensation
    codes = {m.code: m.no_compensation for m in db.query(MarkCode)}
    assert {c for c, flag in codes.items() if flag} == {"р", "и"}


def test_too_few_submitted_days_never_flag_anyone(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 4)
    s1, s2 = _students(db, curator_group, days[0])[:2]
    _fill(db, curator_group, curator_user, days, {s1.id: ["н", "н", "н"], s2.id: ["б", "б"]})
    _, rates = _rates(db, curator_group, days[-1])
    assert rates[s1.id].days == 4 and rates[s1.id].percent == 25.0
    assert not rates[s1.id].is_risk and not rates[s2.id].needs_compensation  # меньше risk_min_days — процент случаен


def test_unsubmitted_days_do_not_count_and_semester_starts_fresh(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 6)
    s1 = _students(db, curator_group, days[0])[0]
    for i, day in enumerate(days[:5]):
        _submit(db, curator_group, curator_user, day, {s1.id: "н"} if i == 0 else {})
    _, rates = _rates(db, curator_group, days[5])  # шестой день не сдан
    assert (rates[s1.id].days, rates[s1.id].absent) == (5, 1)
    assert attendance_service.semester_start(datetime.date(2026, 10, 6)) == datetime.date(2026, 9, 1)
    assert attendance_service.semester_start(datetime.date(2027, 1, 20)) == datetime.date(2026, 9, 1)
    assert attendance_service.semester_start(datetime.date(2027, 2, 1)) == datetime.date(2027, 2, 1)
    assert attendance_service.semester_start(datetime.date(2027, 6, 30)) == datetime.date(2027, 2, 1)
    _, spring = _rates(db, curator_group, datetime.date(2027, 3, 1))
    assert spring[s1.id].days == 0 and spring[s1.id].percent is None and not spring[s1.id].is_risk  # новый семестр — с нуля


def test_attention_list_has_risk_first_then_compensation(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3, s4 = _students(db, curator_group, days[0])[:4]
    _fill(db, curator_group, curator_user, days, {
        s1.id: ["н"] * 5,      # риск, 50 %
        s2.id: ["б"] * 7,      # восполнить, 30 %
        s3.id: ["з"] * 2,      # восполнить, 80 %
        s4.id: ["н"],          # 90 % — никуда
    })
    as_of = days[-1]
    rows = [r for r in stats_service.risk_students(db, as_of) if r["student_id"] in (s1.id, s2.id, s3.id, s4.id)]
    assert [(r["student_id"], r["category"]) for r in rows] == [(s1.id, "risk"), (s2.id, "compensation"), (s3.id, "compensation")]
    assert (rows[0]["attendance_percent"], rows[0]["days"], rows[0]["absent"], rows[0]["absent_unexcused"]) == (50.0, 10, 5, 5)
    assert rows[0]["unexcused_percent"] == 50.0 and rows[1]["absent_unexcused"] == 0
    assert rows[0]["streak"] == 0 and rows[0]["group_code"] == curator_group.code


def test_dashboards_endpoint_returns_category(client, admin_headers, imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2 = _students(db, curator_group, days[0])[:2]
    _fill(db, curator_group, curator_user, days, {s1.id: ["н"] * 5, s2.id: ["б"] * 3})
    r = client.get(f"/dashboards/risk-students?as_of_date={days[-1]}", headers=admin_headers)
    assert r.status_code == 200
    by_id = {x["student_id"]: x for x in r.json()}
    assert by_id[s1.id]["category"] == "risk" and by_id[s1.id]["unexcused_percent"] == 50.0
    assert by_id[s2.id]["category"] == "compensation" and by_id[s2.id]["attendance_percent"] == 70.0


def test_journal_shows_both_statuses_and_settings(client, curator_headers, imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2, s3 = _students(db, curator_group, days[0])[:3]
    _fill(db, curator_group, curator_user, days, {s1.id: ["н"] * 5, s2.id: ["б"] * 3})
    entries = {e["student_id"]: e for e in client.get(f"/curator/groups/{curator_group.id}/day?date={days[-1]}", headers=curator_headers).json()["entries"]}
    assert entries[s1.id]["is_risk"] is True and entries[s1.id]["unexcused_percent"] == 50.0
    assert entries[s1.id]["needs_compensation"] is False
    assert entries[s2.id]["is_risk"] is False and entries[s2.id]["needs_compensation"] is True and entries[s2.id]["attendance_percent"] == 70.0
    assert entries[s3.id]["is_risk"] is False and entries[s3.id]["needs_compensation"] is False
    settings = client.get("/curator/settings", headers=curator_headers).json()
    assert settings == {"risk_unexcused_percent": 40.0, "risk_attendance_percent": 85.0, "risk_min_days": 5, "compensation_reopen_days": 3}


def test_individual_work_ignores_excused_absences(imported, db, curator_group, curator_user):
    days = _days(db, curator_group, 10)
    s1, s2 = _students(db, curator_group, days[0])[:2]
    _fill(db, curator_group, curator_user, days, {
        s1.id: [None, "н", None, "н", None, "н", None, "н", "н"],  # 50 % без причины → риск, нужна работа
        s2.id: ["б"] * 9,                                           # 10 % посещаемости, но больничный — работа не нужна
    })
    by_id = {r.student_id: r for r in individual_work_service.group_overview(db, curator_group.id, days[-1])}
    assert by_id[s1.id].is_risk and by_id[s1.id].needs_attention
    assert s2.id not in by_id


# ---------- «Восполнить пропуски»: куратор закрывает комментарием ----------

@pytest.fixture()
def compensation_case(db, curator_group, curator_user, imported, monkeypatch):
    """Студент 0 — больничный 3 дня из 10 (восполнить), студент 1 — риск; «сегодня» для эндпоинтов — последний день."""
    days = _days(db, curator_group, 16)
    s0, s1 = _students(db, curator_group, days[0])[:2]
    _fill(db, curator_group, curator_user, days[:10], {s0.id: ["б"] * 3, s1.id: ["н"] * 5})
    today = {"day": days[9]}
    monkeypatch.setattr(curator_router, "today_local", lambda: today["day"])
    return {"days": days, "s0": s0, "s1": s1, "today": today}


def test_curator_sees_and_closes_compensation(client, curator_headers, curator_group, db, compensation_case):
    s0 = compensation_case["s0"]
    url = f"/curator/groups/{curator_group.id}/compensation"
    body = client.get(url, headers=curator_headers).json()
    assert [r["student_id"] for r in body["students"]] == [s0.id]
    row = body["students"][0]
    assert (row["attendance_percent"], row["absent_to_compensate"], row["last_closed_on"]) == (70.0, 3, None)
    assert row["by_mark"] == [{"name": "Больничный лист", "count": 3}] and body["closed"] == []
    summary = next(g for g in client.get("/curator/groups", headers=curator_headers).json() if g["id"] == curator_group.id)
    assert (summary["risk_count"], summary["compensation_count"]) == (1, 1)

    r = client.post(f"{url}/{s0.id}", headers=curator_headers, json={"comment": "  Сдал конспекты и тест  "})
    assert r.status_code == 204, r.text
    body = client.get(url, headers=curator_headers).json()
    assert body["students"] == []
    assert body["closed"][0]["student_id"] == s0.id and body["closed"][0]["comment"] == "Сдал конспекты и тест"
    assert body["closed"][0]["closed_on"] == str(compensation_case["days"][9]) and body["closed"][0]["author_name"]
    assert db.query(AuditLog).filter(AuditLog.action == "absence_compensation.close").count() == 1


def test_closed_compensation_reopens_after_three_new_absences(client, curator_headers, curator_group, curator_user, db, compensation_case):
    days, s0, today = compensation_case["days"], compensation_case["s0"], compensation_case["today"]
    url = f"/curator/groups/{curator_group.id}/compensation"
    assert client.post(f"{url}/{s0.id}", headers=curator_headers, json={"comment": "Отработал"}).status_code == 204
    _fill(db, curator_group, curator_user, days[10:12], {s0.id: ["з", "з"]})  # два новых пропуска — ещё рано
    today["day"] = days[11]
    assert client.get(url, headers=curator_headers).json()["students"] == []
    _fill(db, curator_group, curator_user, days[12:13], {s0.id: ["б"]})  # третий — снова в списке
    today["day"] = days[12]
    row = client.get(url, headers=curator_headers).json()["students"][0]
    assert row["student_id"] == s0.id and row["last_closed_on"] == str(days[9])


def test_close_validates_comment_and_status(client, curator_headers, curator_group, compensation_case):
    url = f"/curator/groups/{curator_group.id}/compensation"
    s0, s1 = compensation_case["s0"], compensation_case["s1"]
    assert client.post(f"{url}/{s0.id}", headers=curator_headers, json={"comment": ""}).status_code == 422
    assert client.post(f"{url}/{s0.id}", headers=curator_headers, json={"comment": "   "}).status_code == 400
    risky = client.post(f"{url}/{s1.id}", headers=curator_headers, json={"comment": "Беседа"})
    assert risky.status_code == 409  # студенту из группы риска «восполнять» нечего — с ним индивидуальная работа
    assert client.post(f"{url}/999999", headers=curator_headers, json={"comment": "x"}).status_code == 404


def test_close_needs_access_to_group(client, db, curator_group, db_second_curator, compensation_case):
    from tests.conftest import _login

    other = _login(client, db_second_curator.username, "SecondCura#58x!")
    url = f"/curator/groups/{curator_group.id}/compensation"
    assert client.get(url, headers=other).status_code == 403
    assert client.post(f"{url}/{compensation_case['s0'].id}", headers=other, json={"comment": "x"}).status_code == 403
    assert db.query(AbsenceCompensation).count() == 0


def test_dept_head_can_close_in_own_department(client, dept_head_headers, curator_group, compensation_case):
    """Те же права, что на отметки в журнале группы: зав. отделением — в своём отделении."""
    url = f"/curator/groups/{curator_group.id}/compensation"
    assert client.post(f"{url}/{compensation_case['s0'].id}", headers=dept_head_headers, json={"comment": "Проверено"}).status_code == 204


def test_mark_code_flag_is_editable_by_reference_editor(client, admin_headers, imported, db):
    sick = db.query(MarkCode).filter(MarkCode.code == "б").one()
    r = client.patch(f"/admin/mark-codes/{sick.id}", headers=admin_headers, json={"no_compensation": True})
    assert r.status_code == 200 and r.json()["no_compensation"] is True
    codes = {c["code"]: c for c in client.get("/curator/mark-codes", headers=admin_headers).json()}
    assert codes["б"]["no_compensation"] is True and codes["н"]["no_compensation"] is False


def test_rates_query_count_does_not_grow_with_students(imported, db):
    from sqlalchemy import event

    students = db.query(Student).all()
    queries = []

    def count(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        attendance_service.attendance_rates_bulk(db, students, START)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert len(students) > 500 and len(queries) <= 4, len(queries)
