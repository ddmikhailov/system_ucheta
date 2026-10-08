"""Питание: выбор по студентам, недельная подача, правки по дням до 10:00, прогноз, свод и выгрузка."""
import datetime

import pytest

from app.models import (
    AttendanceMark, Department, DaySubmission, MarkCode, MealDayOverride, Student, StudentProfile, StudyGroup, Task,
    TaskAssignment,
)
from app.services import meal_service

MON = datetime.date(2030, 1, 14)  # понедельник недели, на которую подают
PREV_MON = MON - datetime.timedelta(days=7)


def at(day: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(hour, minute))


def students_of(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).all()


# ---------- формулы ----------

@pytest.mark.parametrize("eaters,percent,expected", [
    (20, 80.0, 18),    # 20 × 90 %
    (20, 95.0, 20),    # потолок — число питающихся
    (25, 71.5, 20),    # 25 × 81,5 % = 20,375 → 20
    (7, 50.0, 4),      # 7 × 60 % = 4,2 → 4
    (10, 55.0, 7),     # 10 × 65 % = 6,5 → 7 (округление вверх от .5)
    (20, None, 20),    # нет данных о посещаемости — столько, сколько питающихся
    (0, 80.0, 0),
])
def test_forecast_is_eaters_times_attendance_plus_ten_points_capped(eaters, percent, expected):
    assert meal_service.forecast_count(eaters, percent) == expected


def test_hint_is_the_same_without_the_extra_ten_points():
    assert meal_service.hint_count(20, 80.0) == 16
    assert meal_service.hint_count(20, None) == 20


def test_deadlines():
    assert meal_service.submit_deadline(MON) == at(MON - datetime.timedelta(days=4), 16)   # четверг 16:00 прошлой недели
    assert meal_service.task_appears_at(MON) == at(PREV_MON, 9)                            # понедельник 09:00 прошлой недели


# ---------- кто питается ----------

def test_everyone_eats_by_default_and_toggle_works(client, curator_headers, curator_group, db):
    r = client.get(f"/meals/groups/{curator_group.id}", headers=curator_headers)
    assert r.status_code == 200
    body = r.json()
    n = len(students_of(db, curator_group))
    assert body["eaters"] == n and all(s["eats"] for s in body["students"]) and body["can_edit"] is True

    sid = body["students"][0]["student_id"]
    assert client.put(f"/meals/groups/{curator_group.id}/students/{sid}", headers=curator_headers, json={"eats": False}).status_code == 204
    again = client.get(f"/meals/groups/{curator_group.id}", headers=curator_headers).json()
    assert again["eaters"] == n - 1
    assert next(s for s in again["students"] if s["student_id"] == sid)["eats"] is False


def test_contract_student_never_eats_and_cannot_be_switched_on(client, curator_headers, curator_group, db):
    s = students_of(db, curator_group)[0]
    db.add(StudentProfile(student_id=s.id, funding="contract"))
    db.commit()
    body = client.get(f"/meals/groups/{curator_group.id}", headers=curator_headers).json()
    row = next(x for x in body["students"] if x["student_id"] == s.id)
    assert row["eats"] is False and "договор" in row["locked_reason"]
    assert body["eaters"] == len(students_of(db, curator_group)) - 1
    r = client.put(f"/meals/groups/{curator_group.id}/students/{s.id}", headers=curator_headers, json={"eats": True})
    assert r.status_code == 409


def test_contract_group_nobody_eats(client, curator_headers, curator_group, db):
    curator_group.funding = "contract"
    db.commit()
    body = client.get(f"/meals/groups/{curator_group.id}", headers=curator_headers).json()
    assert body["eaters"] == 0 and all(not s["eats"] and s["locked_reason"] for s in body["students"])
    sid = body["students"][0]["student_id"]
    assert client.put(f"/meals/groups/{curator_group.id}/students/{sid}", headers=curator_headers, json={"eats": True}).status_code == 409


def test_student_from_another_group_is_rejected(client, curator_headers, curator_group, db):
    other = db.query(Student).filter(Student.study_group_id != curator_group.id).first()
    r = client.put(f"/meals/groups/{curator_group.id}/students/{other.id}", headers=curator_headers, json={"eats": False})
    assert r.status_code == 404


# ---------- подача недели и правки дней ----------

def test_submit_week_validates_and_applies_to_all_study_days(db, curator_group, curator_user):
    n = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON, 10))[curator_group.id].eaters
    with pytest.raises(Exception) as bad:
        meal_service.submit_week(db, curator_user, curator_group, MON, n + 1, at(PREV_MON, 10))
    assert "больше" in str(bad.value.detail)

    week = meal_service.submit_week(db, curator_user, curator_group, MON, n - 2, at(PREV_MON, 10))
    assert week.status == "submitted" and len(week.days) >= 5
    assert {d.count for d in week.days} == {n - 2} and {d.source for d in week.days} == {"submitted"}
    assert all(d.date.weekday() < 6 for d in week.days)


def test_unsubmitted_week_shows_forecast_and_status_follows_the_deadline(db, curator_group):
    before = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON, 10))[curator_group.id]
    after = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON + datetime.timedelta(days=3), 17))[curator_group.id]
    assert before.status == "pending" and after.status == "forecast"
    assert {d.source for d in after.days} == {"forecast"}


def test_day_can_be_edited_until_ten_of_the_previous_study_day(db, curator_group, curator_user):
    n = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON, 10))[curator_group.id].eaters
    meal_service.submit_week(db, curator_user, curator_group, MON, n, at(PREV_MON, 10))
    tuesday = MON + datetime.timedelta(days=1)

    # Понедельник 09:59 — вторник ещё можно править; 10:00 — уже нет.
    week = meal_service.set_day_count(db, curator_user, curator_group, tuesday, n - 3, at(MON, 9, 59))
    assert next(d for d in week.days if d.date == tuesday).source == "edited"
    with pytest.raises(Exception) as late:
        meal_service.set_day_count(db, curator_user, curator_group, tuesday, n - 1, at(MON, 10, 0))
    assert late.value.status_code == 409 and "10:00" in late.value.detail


def test_day_edit_can_be_reset_to_the_weekly_number(db, curator_group, curator_user):
    n = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON, 10))[curator_group.id].eaters
    meal_service.submit_week(db, curator_user, curator_group, MON, n, at(PREV_MON, 10))
    tuesday = MON + datetime.timedelta(days=1)
    meal_service.set_day_count(db, curator_user, curator_group, tuesday, n - 1, at(PREV_MON, 11))
    week = meal_service.set_day_count(db, curator_user, curator_group, tuesday, None, at(PREV_MON, 12))
    assert next(d for d in week.days if d.date == tuesday).source == "submitted"


def test_non_study_day_and_too_big_number_are_refused(db, curator_group, curator_user):
    sunday = MON + datetime.timedelta(days=6)
    with pytest.raises(Exception) as e:
        meal_service.set_day_count(db, curator_user, curator_group, sunday, 1, at(PREV_MON, 10))
    assert "не учебный" in e.value.detail
    with pytest.raises(Exception) as e2:
        meal_service.set_day_count(db, curator_user, curator_group, MON + datetime.timedelta(days=1), 999, at(PREV_MON, 10))
    assert "больше" in e2.value.detail


def test_resubmitting_does_not_rewrite_days_that_are_already_closed(db, curator_group, curator_user):
    n = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON, 10))[curator_group.id].eaters
    meal_service.submit_week(db, curator_user, curator_group, MON, n, at(PREV_MON, 10))
    # Среда 11:00 в день не открыта: чт ещё открыт (до 10:00 среды — уже нет), пт — открыт.
    now = at(MON + datetime.timedelta(days=2), 11)
    new_count = max(n - 5, 0)
    week = meal_service.submit_week(db, curator_user, curator_group, MON, new_count, now)
    by_date = {d.date: d for d in week.days}
    day = lambda k: by_date[MON + datetime.timedelta(days=k)]  # noqa: E731
    assert [day(k).count for k in (0, 1, 2, 3)] == [n, n, n, n]            # закрытые дни (Пн–Чт) сохранили прежнее число
    assert [day(k).open for k in (0, 1, 2, 3)] == [False, False, False, False]
    assert day(4).open and day(4).count == new_count                       # пятница открыта и получила новое число
    assert db.query(MealDayOverride).filter(MealDayOverride.study_group_id == curator_group.id).count() >= 4


def test_submit_week_is_closed_when_all_days_are_past_cutoff(db, curator_group, curator_user):
    with pytest.raises(Exception) as e:
        meal_service.submit_week(db, curator_user, curator_group, MON, 1, at(MON + datetime.timedelta(days=6), 12))
    assert e.value.status_code in (400, 409)


# ---------- прогноз по посещаемости ----------

def test_forecast_uses_last_weeks_attendance_plus_ten_points(db, curator_group, curator_user):
    students = students_of(db, curator_group)
    code = db.query(MarkCode).filter(MarkCode.counts_as_present.is_(False)).first()
    window = [PREV_MON + datetime.timedelta(days=i) for i in range(5)]  # Пн–Пт прошлой недели
    for day in window:
        db.add(DaySubmission(study_group_id=curator_group.id, date=day, submitted_by_user_id=curator_user.id,
                             submitted_at=datetime.datetime.combine(day, datetime.time(9)), is_on_time=True))
        for s in students[:4]:
            db.add(AttendanceMark(student_id=s.id, date=day, mark_code_id=code.id, created_by_user_id=curator_user.id))
    db.commit()
    n = len(students)
    expected_percent = round((n - 4) / n * 100, 1)
    week = meal_service.build_weeks(db, [curator_group], MON, at(MON - datetime.timedelta(days=2), 12))[curator_group.id]
    assert week.percent == expected_percent
    assert week.forecast == meal_service.forecast_count(n, expected_percent) and week.hint == meal_service.hint_count(n, expected_percent)
    assert week.forecast >= week.hint


# ---------- задача «Подать питание» ----------

def test_weekly_task_appears_monday_nine_and_only_once(db, curator_group, curator_user):
    assert meal_service.ensure_weekly_task(db, at(PREV_MON, 8, 59)) is None
    task = meal_service.ensure_weekly_task(db, at(PREV_MON, 9, 0))
    assert task is not None and task.kind == "meal" and task.due_date == PREV_MON + datetime.timedelta(days=3)
    assert "Подать питание" in task.title and task.reviewer_rule == "none"
    assert meal_service.ensure_weekly_task(db, at(PREV_MON, 15)) is None
    assert db.query(Task).filter(Task.kind == "meal").count() == 1
    assert db.query(TaskAssignment).filter(TaskAssignment.task_id == task.id, TaskAssignment.study_group_id == curator_group.id).count() == 1


def test_contract_groups_get_no_task_and_submission_completes_it(db, curator_group, curator_user):
    contract = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    contract.funding = "contract"
    db.commit()
    task = meal_service.ensure_weekly_task(db, at(PREV_MON, 9, 30))
    assert db.query(TaskAssignment).filter(TaskAssignment.task_id == task.id, TaskAssignment.study_group_id == contract.id).count() == 0

    n = meal_service.build_weeks(db, [curator_group], MON, at(PREV_MON, 10))[curator_group.id].eaters
    meal_service.submit_week(db, curator_user, curator_group, MON, n, at(PREV_MON, 10))
    db.commit()
    a = db.query(TaskAssignment).filter(TaskAssignment.task_id == task.id, TaskAssignment.study_group_id == curator_group.id).one()
    assert a.status == "accepted" and a.submitted_at is not None


# ---------- свод, права, выгрузка ----------

def test_meal_manager_sees_the_overview_for_the_whole_college(client, meal_manager_headers, imported):
    r = client.get(f"/meals/overview?week_start={MON}", headers=meal_manager_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] and body["week_start"] == str(MON) and body["dates"]
    first = body["rows"][0]
    assert {"code", "department_name", "eaters", "status", "days"} <= set(first)
    assert body["totals"][body["dates"][0]] == sum(row["days"][0]["count"] for row in body["rows"] if any(d["date"] == body["dates"][0] for d in row["days"]))


def test_meal_manager_can_open_a_group_but_not_edit(client, meal_manager_headers, curator_group):
    r = client.get(f"/meals/groups/{curator_group.id}", headers=meal_manager_headers)
    assert r.status_code == 200 and r.json()["can_edit"] is False
    assert client.post(f"/meals/groups/{curator_group.id}/week", headers=meal_manager_headers, json={"week_start": str(MON), "count": 1}).status_code == 403
    sid = r.json()["students"][0]["student_id"]
    assert client.put(f"/meals/groups/{curator_group.id}/students/{sid}", headers=meal_manager_headers, json={"eats": False}).status_code == 403


def test_curator_cannot_open_the_overview_or_a_foreign_group(client, curator_headers, curator_group, db):
    assert client.get(f"/meals/overview?week_start={MON}", headers=curator_headers).status_code == 403
    other = db.query(StudyGroup).filter(StudyGroup.id != curator_group.id).first()
    assert client.get(f"/meals/groups/{other.id}", headers=curator_headers).status_code == 403


def test_dept_head_sees_only_own_department(client, dept_head_headers, dept_head_user, db, imported):
    other_dept = Department(name="Другое отделение")
    db.add(other_dept)
    db.flush()
    foreign = StudyGroup(code="ЧУЖ111", course=1, department_id=other_dept.id)
    db.add(foreign)
    db.flush()
    db.add(Student(last_name="Тестов", first_name="Тест", study_group_id=foreign.id, enrolled_at=datetime.date(2020, 9, 1)))
    db.commit()
    rows = client.get(f"/meals/overview?week_start={MON}", headers=dept_head_headers).json()["rows"]
    assert rows and all(r["department_id"] == dept_head_user.department_id for r in rows)
    assert client.get(f"/meals/groups/{foreign.id}", headers=dept_head_headers).status_code == 403


def test_overview_excludes_contract_groups(client, admin_headers, imported, db):
    group = db.query(StudyGroup).first()
    group.funding = "contract"
    db.commit()
    rows = client.get(f"/meals/overview?week_start={MON}", headers=admin_headers).json()["rows"]
    assert group.code not in {r["code"] for r in rows}


def test_overview_requires_monday(client, admin_headers):
    assert client.get(f"/meals/overview?week_start={MON + datetime.timedelta(days=1)}", headers=admin_headers).status_code == 400


def test_export_has_a_sheet_per_department_with_totals(client, admin_headers, imported):
    import io

    from openpyxl import load_workbook

    r = client.get(f"/meals/export?week_start={MON}", headers=admin_headers)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames
    ws = wb[wb.sheetnames[0]]
    assert ws["A1"].value.startswith("Питание на неделю")
    assert ws.cell(row=2, column=2).value == "Группа"
    assert ws.cell(row=ws.max_row, column=3).value == "Итого"


def test_meal_manager_has_no_other_permissions(client, meal_manager_headers, curator_group):
    """«Ответственная по питанию» видит только питание: остальные разделы закрыты или пусты."""
    for path in ("/admin/users", "/admin/groups", "/admin/departments", "/dashboards/day?date=2026-10-08",
                 "/students?q=а", "/export/excel?date_from=2026-10-01&date_to=2026-10-02", "/dossier-import/template"):
        assert client.get(path, headers=meal_manager_headers).status_code == 403, path
    assert client.get(f"/curator/groups/{curator_group.id}/day?date=2026-10-08", headers=meal_manager_headers).status_code == 403
    assert client.get("/curator/groups", headers=meal_manager_headers).json() == []
    assert client.get("/tasks", headers=meal_manager_headers).status_code in (200, 403)
    me = client.get("/auth/me", headers=meal_manager_headers).json()
    assert me["role"] == "meal_manager" and me["groups"] == []


def test_admin_creates_a_meal_manager_without_department_and_she_sees_only_meals(client, admin_headers, imported):
    r = client.post("/admin/users", headers=admin_headers, json={
        "full_name": "Ответственная Питания", "username": "meals.head", "role": "meal_manager", "department_id": 1,
    })
    assert r.status_code == 201, r.text
    assert r.json()["department_id"] is None and r.json()["role"] == "meal_manager"
    pwd = client.post(f"/admin/users/{r.json()['id']}/set-password", headers=admin_headers, json={"password": "MealsHead2026!x"})
    assert pwd.status_code == 200
    token = client.post("/auth/login", json={"username": "meals.head", "password": "MealsHead2026!x"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # временный пароль: сначала смена, дальше — только «Питание»
    assert client.get("/auth/me", headers=headers).json()["must_change_password"] is True


def test_only_admin_may_create_a_meal_manager(client, dept_head_headers, imported):
    r = client.post("/admin/users", headers=dept_head_headers, json={"full_name": "Х", "username": "x.meals", "role": "meal_manager"})
    assert r.status_code == 403
