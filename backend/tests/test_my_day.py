"""«Мой день» (plan-v2.md, этап 6): сводка внимания куратора и текст родителям о пропусках."""
import datetime

import pytest

from app.core.time import today_local
from app.models import CuratorAssignment, Student, StudentProfile, Task, TaskAssignment
from app.services import calendar_service, my_day_service
from app.services import individual_work_service as iw


def _students(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).all()


def _day(delta):
    return str(today_local() + datetime.timedelta(days=delta))


def _build(db, user, today):
    db.expire_all()
    return my_day_service.build_my_day(db, user, today)


def _submit_all_present(client, headers, group, day):
    r = client.post(f"/curator/groups/{group.id}/day/mark-all-present?date={day}", headers=headers)
    assert r.status_code == 200, r.text


@pytest.fixture()
def streaks(monkeypatch):
    """Серия пропусков задаётся тестом: {индекс студента в группе: серия}."""
    holder = {}

    def fake(db, students, as_of, lookback_days=21):
        ids = sorted(s.id for s in students)
        return {sid: holder.get(i, 0) for i, sid in enumerate(ids)}

    monkeypatch.setattr(iw.attendance_service, "consecutive_unexcused_counts_bulk", fake)
    return holder


# ---------- группы: сдан ли день, несданные дни ----------

def test_group_status_goes_from_pending_to_submitted(client, curator_headers, curator_user, curator_group, imported, db, today):
    day = _build(db, curator_user, today)
    assert day.leads_groups is True
    assert [(g.id, g.today_status) for g in day.groups] == [(curator_group.id, "pending")]
    _submit_all_present(client, curator_headers, curator_group, today)
    assert _build(db, curator_user, today).groups[0].today_status == "submitted"


def test_no_study_day_on_a_weekend(db, curator_user, curator_group, imported):
    sunday = today_local()
    while sunday.weekday() != 6:  # воскресенье — выходной у всех курсов
        sunday += datetime.timedelta(days=1)
    group = _build(db, curator_user, sunday).groups[0]
    assert group.today_status == "no_study_day" and group.is_on_time is None


def test_missed_days_are_listed_newest_first_and_capped(client, curator_headers, curator_user, curator_group, imported, db, today):
    db.query(CuratorAssignment).filter(CuratorAssignment.user_id == curator_user.id).update(
        {CuratorAssignment.start_date: today - datetime.timedelta(days=30)})
    db.commit()
    window = calendar_service.study_days_between(
        db, today - datetime.timedelta(days=my_day_service.MISSED_LOOKBACK_DAYS),
        today - datetime.timedelta(days=1), study_group_id=curator_group.id, course=curator_group.course)
    assert len(window) > my_day_service.MAX_MISSED_DATES  # без этого проверка среза бессмысленна

    group = _build(db, curator_user, today).groups[0]
    assert group.missed_total == len(window)
    assert group.missed_dates == sorted(window, reverse=True)[:my_day_service.MAX_MISSED_DATES]

    _submit_all_present(client, curator_headers, curator_group, window[-1])
    after = _build(db, curator_user, today).groups[0]
    assert after.missed_total == len(window) - 1 and window[-1] not in after.missed_dates


def test_days_before_the_curator_took_the_group_are_not_missed(db, curator_user, curator_group, imported, today):
    start = today - datetime.timedelta(days=2)
    db.query(CuratorAssignment).filter(CuratorAssignment.user_id == curator_user.id).update(
        {CuratorAssignment.start_date: start})
    db.commit()
    group = _build(db, curator_user, today).groups[0]
    expected = calendar_service.study_days_between(
        db, start, today - datetime.timedelta(days=1), study_group_id=curator_group.id, course=curator_group.course)
    assert group.missed_total == len(expected) <= 2


# ---------- задачи ----------

def _make_task(client, headers, group, title, due_in=7):
    fields = [{"label": "Сдано", "type": "bool", "required": False}]
    r = client.post("/tasks", headers=headers, json={
        "title": title, "collect_mode": "group", "reviewer_rule": "dept_head",
        "due_date": str(today_local() + datetime.timedelta(days=due_in)), "fields": fields,
        "scope": {"group_ids": [group.id]},
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _set(db, task_id, group, due_in=None, **assignment):
    task = db.get(Task, task_id)
    if due_in is not None:
        task.due_date = today_local() + datetime.timedelta(days=due_in)
    a = db.query(TaskAssignment).filter_by(task_id=task_id, study_group_id=group.id).one()
    for k, v in assignment.items():
        setattr(a, k, v)
    db.commit()
    return a


def test_tasks_block_shows_overdue_returned_and_due_soon_only(client, admin_headers, curator_user, curator_group, imported, db):
    ids = {name: _make_task(client, admin_headers, curator_group, name) for name in
           ("Просрочена", "Возвращена", "Скоро", "Сегодня", "Далеко", "Сдана", "Принята", "Закрыта", "Закрытый шаг")}
    _set(db, ids["Просрочена"], curator_group, due_in=-2)
    _set(db, ids["Возвращена"], curator_group, due_in=5, status="returned")
    _set(db, ids["Скоро"], curator_group, due_in=3)
    _set(db, ids["Сегодня"], curator_group, due_in=0)
    _set(db, ids["Далеко"], curator_group, due_in=4)
    _set(db, ids["Сдана"], curator_group, due_in=1, status="submitted")
    _set(db, ids["Принята"], curator_group, due_in=1, status="accepted")
    _set(db, ids["Закрытый шаг"], curator_group, due_in=1, locked=True)
    db.get(Task, ids["Закрыта"]).due_date = today_local() + datetime.timedelta(days=1)
    db.get(Task, ids["Закрыта"]).is_closed = True
    db.commit()

    tasks = _build(db, curator_user, today_local()).tasks
    assert [(t.title, t.kind, t.days_left) for t in tasks] == [
        ("Просрочена", "overdue", -2), ("Возвращена", "returned", 5),
        ("Сегодня", "due_soon", 0), ("Скоро", "due_soon", 3),
    ]
    assert all(t.group_code == curator_group.code for t in tasks)


def test_overdue_returned_task_is_shown_once_as_overdue(client, admin_headers, curator_user, curator_group, imported, db):
    tid = _make_task(client, admin_headers, curator_group, "Вернули и просрочили")
    _set(db, tid, curator_group, due_in=-1, status="returned")
    tasks = _build(db, curator_user, today_local()).tasks
    assert [(t.kind, t.status) for t in tasks] == [("overdue", "returned")]


# ---------- внимание: индивидуальная работа ----------

def _note(client, headers, sid, **body):
    body.setdefault("kind", "conversation")
    body.setdefault("text", "Беседа")
    r = client.post(f"/students/{sid}/dossier/notes", headers=headers, json=body)
    assert r.status_code == 201, r.text


def test_attention_lists_no_work_overdue_and_due_today_follow_ups(client, curator_headers, curator_user, curator_group, imported, db, streaks):
    st = _students(db, curator_group)
    streaks[0] = 5  # серия, работы нет → нужна работа
    _note(client, curator_headers, st[1].id, occurred_on=_day(-10), follow_up_on=_day(-1))  # просрочено
    _note(client, curator_headers, st[2].id, follow_up_on=_day(0))                           # сегодня
    _note(client, curator_headers, st[3].id, follow_up_on=_day(4))                           # потом
    _note(client, curator_headers, st[4].id)                                                 # без срока
    day = _build(db, curator_user, today_local())
    got = [(a.student_id, a.needs_work, a.follow_up_overdue, a.follow_up_today) for a in day.attention]
    assert got == [
        (st[0].id, True, False, False),
        (st[1].id, False, True, False),
        (st[2].id, False, False, True),
    ]
    assert day.attention_total == 3
    assert day.attention[0].risk_streak == 5 and day.attention[0].group_code == curator_group.code


def test_closed_follow_up_leaves_the_list(client, curator_headers, curator_user, curator_group, imported, db, streaks):
    st = _students(db, curator_group)
    _note(client, curator_headers, st[0].id, occurred_on=_day(-5), follow_up_on=_day(-1))
    assert len(_build(db, curator_user, today_local()).attention) == 1
    note = client.get(f"/students/{st[0].id}/dossier", headers=curator_headers).json()["notes"][0]
    client.put(f"/students/{st[0].id}/dossier/notes/{note['id']}/follow-up", headers=curator_headers, json={"done": True})
    assert _build(db, curator_user, today_local()).attention == []


def test_attention_list_is_capped_but_total_is_honest(client, curator_headers, curator_user, curator_group, imported, db, streaks, monkeypatch):
    monkeypatch.setattr(my_day_service, "MAX_ATTENTION", 2)
    for i in range(4):
        streaks[i] = 4
    day = _build(db, curator_user, today_local())
    assert len(day.attention) == 2 and day.attention_total == 4


# ---------- дни рождения ----------

def _born(db, student, born):
    db.add(StudentProfile(student_id=student.id, birth_date=born))
    db.commit()


def test_birthdays_within_a_week_sorted_with_age(db, curator_user, curator_group, imported):
    today = today_local()
    st = _students(db, curator_group)

    def years_ago(days_ahead, years):
        d = today + datetime.timedelta(days=days_ahead)
        return datetime.date(d.year - years, d.month, d.day)

    _born(db, st[0], years_ago(3, 17))
    _born(db, st[1], years_ago(0, 18))
    _born(db, st[2], years_ago(7, 16))
    _born(db, st[3], years_ago(8, 16))    # за неделей — не попадает
    _born(db, st[4], years_ago(-1, 16))   # вчера — следующий через год
    day = _build(db, curator_user, today)
    assert [(b.student_id, b.days_until, b.turns) for b in day.birthdays] == [
        (st[1].id, 0, 18), (st[0].id, 3, 17), (st[2].id, 7, 16)]
    assert day.birthdays[1].date == today + datetime.timedelta(days=3)
    assert day.birthdays[0].group_code == curator_group.code


def test_students_without_birth_date_are_skipped(db, curator_user, curator_group, imported):
    assert _build(db, curator_user, today_local()).birthdays == []


def test_next_birthday_handles_year_end_and_leap_day():
    d = datetime.date
    assert my_day_service.next_birthday(d(2008, 1, 2), d(2026, 12, 30)) == d(2027, 1, 2)
    assert my_day_service.next_birthday(d(2008, 10, 4), d(2026, 10, 4)) == d(2026, 10, 4)
    assert my_day_service.next_birthday(d(2008, 2, 29), d(2027, 2, 20)) == d(2027, 2, 28)   # невисокосный год
    assert my_day_service.next_birthday(d(2008, 2, 29), d(2028, 2, 20)) == d(2028, 2, 29)


# ---------- доступ и роли ----------

def test_requires_login(client):
    assert client.get("/my-day").status_code == 401


def test_curator_sees_only_own_group(client, curator_headers, db_second_curator, curator_group, imported, db):
    body = client.get("/my-day", headers=curator_headers).json()
    assert body["leads_groups"] is True
    assert [g["id"] for g in body["groups"]] == [curator_group.id]
    assert body["review_waiting"] is None


def test_other_curator_group_is_not_visible(client, curator_group, db_second_curator, imported):
    from tests.conftest import _login
    headers = _login(client, db_second_curator.username, "SecondCurator123!")
    ids = [g["id"] for g in client.get("/my-day", headers=headers).json()["groups"]]
    assert curator_group.id not in ids


def test_admin_has_no_groups_but_gets_review_counter(client, admin_headers, curator_headers, curator_group, imported, db):
    tid = _make_task(client, admin_headers, curator_group, "На проверку")
    a = db.query(TaskAssignment).filter_by(task_id=tid, study_group_id=curator_group.id).one()
    client.put(f"/tasks/assignments/{a.id}/answers", headers=curator_headers,
               json={"group_values": {"f1": True}})
    assert client.post(f"/tasks/assignments/{a.id}/submit", headers=curator_headers).status_code == 200
    body = client.get("/my-day", headers=admin_headers).json()
    assert body["leads_groups"] is False and body["groups"] == [] and body["tasks"] == []
    assert body["attention"] == [] and body["birthdays"] == []
    assert body["review_waiting"]["count"] == 1 and body["review_waiting"]["oldest_submitted_at"]


def test_dept_head_counts_only_own_department_reviews(client, dept_head_headers, dept_head_user, admin_headers, curator_headers, curator_group, imported, db):
    tid = _make_task(client, admin_headers, curator_group, "Отделение")
    a = db.query(TaskAssignment).filter_by(task_id=tid, study_group_id=curator_group.id).one()
    client.put(f"/tasks/assignments/{a.id}/answers", headers=curator_headers, json={"group_values": {"f1": True}})
    client.post(f"/tasks/assignments/{a.id}/submit", headers=curator_headers)
    count = client.get("/my-day", headers=dept_head_headers).json()["review_waiting"]["count"]
    assert count == (1 if curator_group.department_id == dept_head_user.department_id else 0)


# ---------- сообщение родителям о пропусках ----------

def _mark(client, headers, group, student, code, day, comment=None):
    r = client.post(f"/curator/groups/{group.id}/day/submit?date={day}", headers=headers, json={
        "exceptions": [{"student_id": student.id, "mark_code": code, "comment": comment, "basis_reference": None}]})
    assert r.status_code == 200, r.text


def test_absence_message_lists_only_unexcused_marks(client, curator_headers, curator_user, curator_group, imported, db, today):
    s = _students(db, curator_group)[0]
    study = calendar_service.study_days_between(
        db, today - datetime.timedelta(days=10), today, study_group_id=curator_group.id, course=curator_group.course)
    assert len(study) >= 4
    _mark(client, curator_headers, curator_group, s, "н", study[-1])
    _mark(client, curator_headers, curator_group, s, "б", study[-2])   # больничный — причина известна
    _mark(client, curator_headers, curator_group, s, "у", study[-3])
    _mark(client, curator_headers, curator_group, s, "о", study[-4])   # опоздание — присутствовал
    r = client.get(f"/students/{s.id}/absence-message?days=14", headers=curator_headers)
    assert r.status_code == 200
    body = r.json()
    assert [(a["date"], a["code"]) for a in body["absences"]] == [(str(study[-3]), "у"), (str(study[-1]), "н")]
    text = body["text"]
    assert s.full_name in text and curator_group.code in text and curator_user.full_name in text
    assert study[-1].strftime("%d.%m.%Y") in text and "Неуважительная причина" in text
    assert "Больничный" not in text and "Опоздание" not in text


def test_absence_message_is_empty_when_nothing_to_report(client, curator_headers, curator_group, imported, db):
    s = _students(db, curator_group)[0]
    body = client.get(f"/students/{s.id}/absence-message", headers=curator_headers).json()
    assert body == {"days": 14, "absences": [], "text": ""}


def test_absence_message_window_is_clamped_and_old_marks_dropped(client, curator_headers, curator_group, imported, db, today):
    s = _students(db, curator_group)[0]
    study = calendar_service.study_days_between(
        db, today - datetime.timedelta(days=12), today, study_group_id=curator_group.id, course=curator_group.course)
    _mark(client, curator_headers, curator_group, s, "н", study[0])
    short = client.get(f"/students/{s.id}/absence-message?days=1", headers=curator_headers).json()
    assert short["days"] == 1 and short["absences"] == [] and short["text"] == ""  # отметка двенадцатидневной давности
    assert len(client.get(f"/students/{s.id}/absence-message?days=14", headers=curator_headers).json()["absences"]) == 1
    assert client.get(f"/students/{s.id}/absence-message?days=9999", headers=curator_headers).json()["days"] == 60
    assert client.get(f"/students/{s.id}/absence-message?days=0", headers=curator_headers).json()["days"] == 1


def test_absence_message_follows_student_access(client, curator_group, db_second_curator, curator_headers, imported, db, admin_headers):
    from tests.conftest import _login
    s = _students(db, curator_group)[0]
    other = _login(client, db_second_curator.username, "SecondCurator123!")
    assert client.get(f"/students/{s.id}/absence-message", headers=other).status_code == 403
    assert client.get(f"/students/{s.id}/absence-message", headers=admin_headers).status_code == 200
    assert client.get("/students/999999/absence-message", headers=admin_headers).status_code == 404
    assert client.get(f"/students/{s.id}/absence-message").status_code == 401
