"""Периодические задачи: расписание на шаблоне, запуск при открытии платформы."""
import datetime

import pytest

from app.models import AuditLog, Task, TaskTemplate, User
from app.services import task_schedule as sched

D = datetime.date


def _future(days=7):
    return str(D.today() + datetime.timedelta(days=days))


def _template(client, headers, **over):
    body = {"title": "Отчёт о воспитательной работе", "description": "За месяц", "collect_mode": "group",
            "reviewer_rule": "dept_head", "due_date": _future(),
            "fields": [{"label": "Сдано", "type": "bool", "required": True}], "scope": {"all_groups": True}}
    body.update(over)
    task = client.post("/tasks", headers=headers, json=body)
    assert task.status_code == 201, task.text
    r = client.post("/tasks/templates", headers=headers, json={"task_id": task.json()["id"], "name": "Ежемесячный отчёт"})
    assert r.status_code == 201
    return r.json()


def _schedule(client, headers, tid, repeat="monthly", day=1, offset=14):
    return client.put(f"/tasks/templates/{tid}/schedule", headers=headers,
                      json={"repeat": repeat, "repeat_day": day, "due_offset_days": offset})


def _run(db, today):
    db.expire_all()
    return sched.run_due_templates(db, today=today, force=True)


# ---------- даты ----------

@pytest.mark.parametrize("kind,day,frm,expected", [
    ("monthly", 5, D(2026, 10, 4), D(2026, 10, 5)),
    ("monthly", 5, D(2026, 10, 5), D(2026, 10, 5)),
    ("monthly", 5, D(2026, 10, 6), D(2026, 11, 5)),
    ("monthly", 1, D(2026, 12, 15), D(2027, 1, 1)),
    ("semester", 1, D(2026, 10, 4), D(2027, 2, 1)),
    ("semester", 10, D(2026, 9, 3), D(2026, 9, 10)),
    ("semester", 1, D(2027, 2, 2), D(2027, 9, 1)),
    ("semester", 28, D(2026, 2, 28), D(2026, 2, 28)),
])
def test_next_occurrence(kind, day, frm, expected):
    assert sched.next_occurrence(kind, day, frm) == expected


def test_period_labels():
    assert sched.period_label("monthly", D(2026, 10, 1)) == "Октябрь 2026"
    assert sched.period_label("semester", D(2026, 9, 1)) == "осенний семестр 2026"
    assert sched.period_label("semester", D(2027, 2, 1)) == "весенний семестр 2027"


# ---------- настройка расписания ----------

def test_setting_the_schedule_computes_the_next_run(client, admin_headers, curator_group, imported):
    tpl = _template(client, admin_headers)
    assert tpl["repeat"] == "" and tpl["next_run"] is None
    r = _schedule(client, admin_headers, tpl["id"], "monthly", 1, 10)
    assert r.status_code == 200
    body = r.json()
    assert body["repeat"] == "monthly" and body["due_offset_days"] == 10
    assert body["next_run"] == str(sched.next_occurrence("monthly", 1, D.today()))
    off = _schedule(client, admin_headers, tpl["id"], "").json()
    assert off["repeat"] == "" and off["next_run"] is None


def test_schedule_validation_and_rights(client, admin_headers, dept_head_headers, edu_department_headers, curator_group, imported):
    tpl = _template(client, dept_head_headers)
    assert _schedule(client, admin_headers, tpl["id"], "weekly").status_code == 422
    assert _schedule(client, admin_headers, tpl["id"], "monthly", day=31).status_code == 422
    assert _schedule(client, admin_headers, tpl["id"], "monthly", offset=0).status_code == 422
    assert _schedule(client, edu_department_headers, tpl["id"]).status_code == 403  # не автор и не админ
    assert _schedule(client, dept_head_headers, tpl["id"]).status_code == 200
    assert _schedule(client, admin_headers, 99999).status_code == 404


# ---------- запуск ----------

def test_due_template_creates_a_task_with_period_title_and_due_date(client, admin_headers, curator_headers, curator_group, imported, db):
    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "monthly", 1, 10)
    run_day = sched.next_occurrence("monthly", 1, D.today())
    assert _run(db, run_day - datetime.timedelta(days=1)) == 0  # рано
    assert _run(db, run_day) == 1
    task = db.query(Task).filter(Task.template_id == tpl["id"]).one()
    assert task.title == f"Отчёт о воспитательной работе — {sched.period_label('monthly', run_day)}"
    assert task.due_date == run_day + datetime.timedelta(days=10)
    assert task.period_key == run_day.strftime("%Y-%m") and task.collect_mode == "group"
    db.expire_all()
    template = db.get(TaskTemplate, tpl["id"])
    assert template.last_run_date == run_day
    assert template.next_run == sched.next_occurrence("monthly", 1, run_day + datetime.timedelta(days=1))
    assert db.query(AuditLog).filter(AuditLog.action == "task.scheduled_create").count() == 1
    mine = client.get("/tasks/my", headers=curator_headers).json()
    assert any(r["task_id"] == task.id for r in mine)


def test_second_run_on_the_same_day_does_nothing(client, admin_headers, curator_group, imported, db):
    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "monthly", 1)
    day = sched.next_occurrence("monthly", 1, D.today())
    assert _run(db, day) == 1
    assert _run(db, day) == 0
    assert db.query(Task).filter(Task.template_id == tpl["id"]).count() == 1


def test_long_absence_creates_one_current_task_not_a_batch(client, admin_headers, curator_group, imported, db):
    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "monthly", 1)
    first = sched.next_occurrence("monthly", 1, D.today())
    late = first + datetime.timedelta(days=95)  # платформу не открывали три месяца
    assert _run(db, late) == 1
    tasks = db.query(Task).filter(Task.template_id == tpl["id"]).all()
    assert len(tasks) == 1 and tasks[0].period_key == late.strftime("%Y-%m")
    assert tasks[0].due_date >= late  # срок не в прошлом
    db.expire_all()
    assert db.get(TaskTemplate, tpl["id"]).next_run > late


def test_semester_runs_in_september_and_february_only(client, admin_headers, curator_group, imported, db):
    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "semester", 1)
    first = sched.next_occurrence("semester", 1, D.today())
    assert first.month in (2, 9)
    assert _run(db, first) == 1
    db.expire_all()
    following = db.get(TaskTemplate, tpl["id"]).next_run
    assert following.month in (2, 9) and following > first and (following.year, following.month) != (first.year, first.month)
    assert "семестр" in db.query(Task).filter(Task.template_id == tpl["id"]).one().title


def test_unscheduled_templates_never_run(client, admin_headers, curator_group, imported, db):
    _template(client, admin_headers)
    assert _run(db, D.today() + datetime.timedelta(days=400)) == 0


def test_author_who_can_no_longer_create_tasks_is_skipped_with_a_reason(client, admin_headers, dept_head_headers, dept_head_user, curator_group, imported, db):
    tpl = _template(client, dept_head_headers)
    _schedule(client, dept_head_headers, tpl["id"], "monthly", 1)
    db.query(User).filter(User.id == dept_head_user.id).update({"is_active": False})
    db.commit()
    day = sched.next_occurrence("monthly", 1, D.today())
    assert _run(db, day) == 0
    db.expire_all()
    template = db.get(TaskTemplate, tpl["id"])
    assert "автор шаблона" in template.last_error and template.next_run > day  # не зацикливается
    assert db.query(Task).filter(Task.template_id == tpl["id"]).count() == 0
    assert db.query(AuditLog).filter(AuditLog.action == "task.scheduled_skip").count() == 1
    shown = [t for t in client.get("/tasks/templates", headers=admin_headers).json() if t["id"] == tpl["id"]][0]
    assert "автор шаблона" in shown["last_error"]


def test_dept_head_template_keeps_the_department_scope_at_launch(client, dept_head_headers, curator_group, imported, db):
    """Запуск идёт с правами автора: зав. отделением получает только группы своего отделения."""
    tpl = _template(client, dept_head_headers)
    _schedule(client, dept_head_headers, tpl["id"], "monthly", 1)
    day = sched.next_occurrence("monthly", 1, D.today())
    assert _run(db, day) == 1
    task = db.query(Task).filter(Task.template_id == tpl["id"]).one()
    assert task.assignments and all(a.study_group.department_id == curator_group.department_id for a in task.assignments)


def test_launch_happens_on_platform_open(client, admin_headers, curator_headers, curator_group, imported, db):
    """Колокольчик при входе опрашивает /notifications/unread-count: там и запускается расписание."""
    from app.services import task_service

    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "monthly", 1)
    db.query(TaskTemplate).filter(TaskTemplate.id == tpl["id"]).update({"next_run": D.today()})
    db.commit()
    task_service.reset_reminder_throttle()
    assert client.get("/notifications/unread-count", headers=curator_headers).status_code == 200
    assert db.query(Task).filter(Task.template_id == tpl["id"]).count() == 1
    notes = [n["kind"] for n in client.get("/notifications", headers=curator_headers).json()]
    assert "task_assigned" in notes


def test_deleting_a_template_keeps_its_tasks(client, admin_headers, curator_group, imported, db):
    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "monthly", 1)
    assert _run(db, sched.next_occurrence("monthly", 1, D.today())) == 1
    assert client.delete(f"/tasks/templates/{tpl['id']}", headers=admin_headers).status_code == 204
    db.expire_all()
    tasks = db.query(Task).filter(Task.title.like("Отчёт о воспитательной работе —%")).all()
    assert len(tasks) == 1 and tasks[0].template_id is None


def test_stale_claim_does_not_launch_twice(client, admin_headers, curator_group, imported, db):
    """Два одновременных опроса: второй держит устаревшее next_run — условный UPDATE его отсекает."""
    tpl = _template(client, admin_headers)
    _schedule(client, admin_headers, tpl["id"], "monthly", 1)
    day = sched.next_occurrence("monthly", 1, D.today())
    stale = db.get(TaskTemplate, tpl["id"])
    stale_next = stale.next_run
    assert _run(db, day) == 1
    stale = db.get(TaskTemplate, tpl["id"])
    stale.next_run = stale_next  # как будто опрос прочитал шаблон до первого запуска
    assert sched._run_one(db, stale, day) == 0
    assert db.query(Task).filter(Task.template_id == tpl["id"]).count() == 1
    db.expire_all()
    assert db.get(TaskTemplate, tpl["id"]).last_error is None  # отсечён молча на захвате, а не «пропуском с ошибкой»
