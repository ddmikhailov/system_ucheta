"""Набор «Адаптация первого курса»: кто ставит, кому приходит, защита от повторного запуска."""
import datetime

import pytest

from app.core.time import today_local
from app.models import Task, TaskAssignment

URL = "/tasks/starter-sets/first-year"


def _start(days=0):
    return str(today_local() + datetime.timedelta(days=days))


@pytest.fixture()
def first_year_group(db, curator_group):
    curator_group.course = 1
    db.commit()
    return curator_group


def test_admin_launches_six_weekly_tasks_for_first_year_groups(client, admin_headers, curator_headers, first_year_group, db):
    r = client.post(URL, headers=admin_headers, json={"start_date": _start()})
    assert r.status_code == 201, r.text
    tasks = r.json()
    assert len(tasks) == 6 and all(t["title"].startswith("Адаптация 1 курса:") for t in tasks)
    dues = [datetime.date.fromisoformat(t["due_date"]) for t in tasks]
    assert dues == [today_local() + datetime.timedelta(days=7 * w - 1) for w in range(1, 7)]
    assert db.query(TaskAssignment).filter(TaskAssignment.study_group_id == first_year_group.id).count() == 6
    mine = client.get("/tasks/my", headers=curator_headers).json()
    assert {t["id"] for t in tasks} <= {m["task_id"] for m in mine}


def test_other_courses_do_not_get_tasks(client, admin_headers, first_year_group, db):
    from app.models import StudyGroup
    second = db.query(StudyGroup).filter(StudyGroup.id != first_year_group.id).first()
    if second is not None:
        second.course = 3
        db.commit()
    client.post(URL, headers=admin_headers, json={"start_date": _start()})
    assert db.query(TaskAssignment).join(StudyGroup, StudyGroup.id == TaskAssignment.study_group_id).filter(
        StudyGroup.course != 1).count() == 0


def test_repeat_launch_is_rejected(client, admin_headers, first_year_group, db):
    assert client.post(URL, headers=admin_headers, json={"start_date": _start()}).status_code == 201
    assert client.post(URL, headers=admin_headers, json={"start_date": _start()}).status_code == 409
    assert db.query(Task).count() == 6


def test_no_first_year_groups_gives_clear_error(client, admin_headers, curator_group, db):
    curator_group.course = 3
    db.commit()
    from app.models import StudyGroup
    db.query(StudyGroup).update({StudyGroup.course: 3})
    db.commit()
    r = client.post(URL, headers=admin_headers, json={"start_date": _start()})
    assert r.status_code == 400 and db.query(Task).count() == 0


def test_start_in_past_is_rejected(client, admin_headers, first_year_group):
    assert client.post(URL, headers=admin_headers, json={"start_date": _start(-1)}).status_code == 400


def test_dept_head_launches_only_for_own_department(client, dept_head_headers, dept_head_user, first_year_group, db):
    r = client.post(URL, headers=dept_head_headers, json={"start_date": _start()})
    in_scope = first_year_group.department_id == dept_head_user.department_id
    assert r.status_code == (201 if in_scope else 400)


@pytest.mark.parametrize("headers_name,expected", [("curator_headers", 403), ("admin_headers", 200)])
def test_descriptor_is_for_task_managers(client, request, first_year_group, headers_name, expected):
    r = client.get(URL, headers=request.getfixturevalue(headers_name))
    assert r.status_code == expected
    if expected == 200:
        assert len(r.json()) == 6


def test_curator_cannot_launch_and_anonymous_gets_401(client, curator_headers, first_year_group):
    assert client.post(URL, headers=curator_headers, json={"start_date": _start()}).status_code == 403
    assert client.post(URL, json={"start_date": _start()}).status_code == 401
