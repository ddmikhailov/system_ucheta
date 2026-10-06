"""Журнал индивидуальной работы: заметки с датой и «вернуться к вопросу», обзор группы, напоминания."""
import datetime

import pytest

from app.core.time import today_local
from app.models import AuditLog, InAppNotification, Student, StudentNote
from app.services import individual_work_service as svc
from app.services import task_service


def _students(db, group):
    return db.query(Student).filter(Student.study_group_id == group.id).order_by(Student.id).all()


def _note(client, headers, sid, **body):
    body.setdefault("kind", "conversation")
    body.setdefault("text", "Беседа о пропусках")
    return client.post(f"/students/{sid}/dossier/notes", headers=headers, json=body)


def _day(delta):
    return str(today_local() + datetime.timedelta(days=delta))


@pytest.fixture()
def attendance(monkeypatch):
    """Посещаемость студентов задаётся тестом: {индекс студента в группе: процент}; остальные — 100 %."""
    holder = {}

    def fake(db, students, as_of):
        ids = sorted(s.id for s in students)  # номера в тестах — по порядку id, как в _students
        return {sid: svc_rate(holder.get(i, 100.0)) for i, sid in enumerate(ids)}

    monkeypatch.setattr(svc.attendance_service, "attendance_rates_bulk", fake)
    return holder


def svc_rate(percent):
    from app.services.attendance_service import AttendanceRate
    return AttendanceRate(days=20, absent=round(20 * (100 - percent) / 100), percent=percent)



# ---------- заметки ----------

def test_note_defaults_to_today_and_accepts_dates(client, curator_headers, curator_group, imported, db):
    s = _students(db, curator_group)[0]
    r = _note(client, curator_headers, s.id)
    assert r.status_code == 201 and r.json()["occurred_on"] == _day(0) and r.json()["follow_up_on"] is None
    r = _note(client, curator_headers, s.id, kind="parent_invited", occurred_on=_day(-3), follow_up_on=_day(4))
    body = r.json()
    assert body["kind"] == "parent_invited" and body["occurred_on"] == _day(-3) and body["follow_up_on"] == _day(4)
    assert body["follow_up_done"] is False
    listed = client.get(f"/students/{s.id}/dossier", headers=curator_headers).json()["notes"]
    assert {n["kind"] for n in listed} == {"conversation", "parent_invited"}


def test_new_note_kinds_and_date_validation(client, curator_headers, curator_group, imported, db):
    s = _students(db, curator_group)[0]
    for kind in ("prevention_council", "home_visit"):
        assert _note(client, curator_headers, s.id, kind=kind).status_code == 201
    assert _note(client, curator_headers, s.id, kind="nonsense").status_code == 422
    future = _note(client, curator_headers, s.id, occurred_on=_day(2))
    assert future.status_code == 400 and "в будущем" in future.json()["detail"]
    early = _note(client, curator_headers, s.id, occurred_on=_day(-2), follow_up_on=_day(-5))
    assert early.status_code == 400 and "не раньше" in early.json()["detail"]


def test_follow_up_can_be_closed_and_reopened_by_anyone_with_access(client, curator_headers, admin_headers, curator_group, imported, db):
    s = _students(db, curator_group)[0]
    note = _note(client, curator_headers, s.id, follow_up_on=_day(3)).json()
    url = f"/students/{s.id}/dossier/notes/{note['id']}/follow-up"
    done = client.put(url, headers=admin_headers, json={"done": True})
    assert done.status_code == 200 and done.json()["follow_up_done"] is True
    assert client.put(url, headers=curator_headers, json={"done": False}).json()["follow_up_done"] is False
    plain = _note(client, curator_headers, s.id).json()
    bad = client.put(f"/students/{s.id}/dossier/notes/{plain['id']}/follow-up", headers=curator_headers, json={"done": True})
    assert bad.status_code == 400 and "нет даты" in bad.json()["detail"]
    assert client.put(f"/students/{s.id}/dossier/notes/99999/follow-up", headers=curator_headers, json={"done": True}).status_code == 404
    assert db.query(AuditLog).filter(AuditLog.action == "dossier.follow_up_done").count() == 1


# ---------- обзор группы ----------

def test_overview_lists_risk_students_and_those_with_work(client, curator_headers, curator_group, imported, db, attendance):
    st = _students(db, curator_group)
    attendance[0] = 60.0  # посещаемость 60 % (риск), работы нет → нужна работа
    attendance[1] = 70.0  # посещаемость 70 % (риск), беседа вчера → внимание не требуется
    _note(client, curator_headers, st[1].id, occurred_on=_day(-1))
    _note(client, curator_headers, st[2].id, kind="call", occurred_on=_day(-40))  # давняя работа, без риска
    r = client.get(f"/individual-work/groups/{curator_group.id}", headers=curator_headers)
    assert r.status_code == 200
    body = r.json()
    rows = {x["student_id"]: x for x in body["rows"]}
    assert set(rows) == {st[0].id, st[1].id, st[2].id}  # остальных нет: ни риска, ни записей
    assert rows[st[0].id]["needs_attention"] is True and rows[st[0].id]["work_count"] == 0
    assert rows[st[1].id]["needs_attention"] is False and rows[st[1].id]["last_work_on"] == _day(-1)
    assert rows[st[2].id]["is_risk"] is False and rows[st[2].id]["last_work_on"] == _day(-40)
    assert body["rows"][0]["student_id"] == st[0].id  # «нужна работа» — первой
    assert body["no_work_days"] == 14


def test_old_work_does_not_count_as_recent(client, curator_headers, curator_group, imported, db, attendance):
    st = _students(db, curator_group)
    attendance[0] = 70.0
    _note(client, curator_headers, st[0].id, occurred_on=_day(-30))
    row = client.get(f"/individual-work/groups/{curator_group.id}", headers=curator_headers).json()["rows"][0]
    assert row["needs_attention"] is True and row["work_count"] == 1


def test_non_work_notes_do_not_count(client, curator_headers, curator_group, imported, db, attendance):
    st = _students(db, curator_group)
    attendance[0] = 70.0
    _note(client, curator_headers, st[0].id, kind="incident")
    _note(client, curator_headers, st[0].id, kind="other")
    row = client.get(f"/individual-work/groups/{curator_group.id}", headers=curator_headers).json()["rows"][0]
    assert row["work_count"] == 0 and row["needs_attention"] is True


def test_follow_up_dates_in_overview(client, curator_headers, curator_group, imported, db, attendance):
    st = _students(db, curator_group)
    _note(client, curator_headers, st[0].id, occurred_on=_day(-10), follow_up_on=_day(-1))
    later = _note(client, curator_headers, st[0].id, follow_up_on=_day(5)).json()
    row = client.get(f"/individual-work/groups/{curator_group.id}", headers=curator_headers).json()["rows"][0]
    assert row["next_follow_up_on"] == _day(-1) and row["follow_up_overdue"] is True
    # просроченную закрыли — ближайшей становится следующая, просрочки нет
    first = db.query(StudentNote).filter(StudentNote.student_id == st[0].id, StudentNote.follow_up_on == today_local() - datetime.timedelta(days=1)).one()
    client.put(f"/students/{st[0].id}/dossier/notes/{first.id}/follow-up", headers=curator_headers, json={"done": True})
    row = client.get(f"/individual-work/groups/{curator_group.id}", headers=curator_headers).json()["rows"][0]
    assert row["next_follow_up_on"] == later["follow_up_on"] and row["follow_up_overdue"] is False


def test_access_to_groups(client, curator_headers, dept_head_headers, admin_headers, curator_group, imported, db):
    foreign = db.query(Student).filter(Student.study_group_id != curator_group.id).first()
    mine = client.get("/individual-work/groups", headers=curator_headers).json()
    assert [g["id"] for g in mine] == [curator_group.id]
    assert client.get(f"/individual-work/groups/{curator_group.id}", headers=admin_headers).status_code == 200
    if foreign is not None:
        assert client.get(f"/individual-work/groups/{foreign.study_group_id}", headers=curator_headers).status_code == 403
    assert client.get("/individual-work/groups/99999", headers=curator_headers).status_code == 403


# ---------- напоминания ----------

def test_follow_up_reminder_goes_to_the_author_once(client, curator_headers, admin_headers, curator_user, curator_group, imported, db):
    s = _students(db, curator_group)[0]
    _note(client, curator_headers, s.id, occurred_on=_day(-5), follow_up_on=_day(0))
    _note(client, curator_headers, s.id, follow_up_on=_day(7))  # срок ещё не наступил

    def poll(headers):
        task_service.reset_reminder_throttle()
        client.get("/notifications/unread-count", headers=headers)

    poll(curator_headers)
    poll(curator_headers)
    kinds = [n for n in client.get("/notifications", headers=curator_headers).json() if n["kind"] == "work_followup"]
    assert len(kinds) == 1
    assert s.full_name in kinds[0]["message"] and kinds[0]["entity_type"] == "student" and kinds[0]["entity_id"] == str(s.id)
    poll(admin_headers)  # не автор — не получает
    assert not [n for n in client.get("/notifications", headers=admin_headers).json() if n["kind"] == "work_followup"]


def test_done_follow_up_gives_no_reminder(client, curator_headers, curator_group, imported, db):
    s = _students(db, curator_group)[0]
    note = _note(client, curator_headers, s.id, occurred_on=_day(-5), follow_up_on=_day(-1)).json()
    client.put(f"/students/{s.id}/dossier/notes/{note['id']}/follow-up", headers=curator_headers, json={"done": True})
    task_service.reset_reminder_throttle()
    client.get("/notifications/unread-count", headers=curator_headers)
    assert db.query(InAppNotification).filter(InAppNotification.kind == "work_followup").count() == 0
