"""Перевод студента в другую группу не должен переписывать историю
посещаемости задним числом (см. TODO.md 3) — старая группа сохраняет то,
что реально было при ней, новая отвечает только с даты перевода.

Эндпоинт переводит студента "с сегодня" (`today_local()`, как и снятие
куратора/заместителя, см. CuratorAssignment) — своей даты вступления в силу
у него нет, поэтому "до перевода" в тестах — фиксированная дата в прошлом
(DAY1), а "после" — сам `today_local()`, а не следующая по календарю дата
(которая может быть не при делах ещё пару строк из-за выходных)."""
import datetime

from app.core.time import today_local
from app.models import StudyGroup
from app.services import attendance_service, stats_service

DAY1 = datetime.date(2026, 9, 21)  # понедельник, учебный день, точно в прошлом


def _two_active_groups(db) -> tuple[StudyGroup, StudyGroup]:
    groups = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).order_by(StudyGroup.id).limit(2).all()
    assert len(groups) == 2
    return groups[0], groups[1]


def test_transfer_preserves_old_group_history(client, admin_headers, imported, db, curator_user):
    group_a, group_b = _two_active_groups(db)
    student = attendance_service.get_active_students(db, group_a.id, DAY1)[0]

    # Отметка "н" в группе A за DAY1 — до перевода.
    attendance_service.submit_day(
        db, group_a.id, DAY1,
        [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=DAY1,
    )

    # Перевод в группу B, эффективно с DAY2.
    r = client.patch(
        f"/admin/students/{student.id}", headers=admin_headers,
        json={"study_group_id": group_b.id},
    )
    assert r.status_code == 200, r.text

    db.commit()
    db.expire_all()

    # Группа A за DAY1 (до перевода) — студент и его "н" всё ещё её.
    roster_a_day1 = attendance_service.get_active_students(db, group_a.id, DAY1)
    assert any(s.id == student.id for s in roster_a_day1)
    stats_a_day1 = stats_service.compute_period_stats(db, DAY1, DAY1, study_group_id=group_a.id)
    assert stats_a_day1.absent_unexcused == 1

    # Группа B за DAY1 — студента там ещё не было.
    roster_b_day1 = attendance_service.get_active_students(db, group_b.id, DAY1)
    assert not any(s.id == student.id for s in roster_b_day1)

    # С today_local() (дата вступления перевода в силу) — наоборот: студент
    # теперь в ростере B, не в A.
    today = today_local()
    roster_a_today = attendance_service.get_active_students(db, group_a.id, today)
    assert not any(s.id == student.id for s in roster_a_today)
    roster_b_today = attendance_service.get_active_students(db, group_b.id, today)
    assert any(s.id == student.id for s in roster_b_today)


def test_transfer_writes_audit_log_and_membership_rows(client, admin_headers, imported, db):
    from app.models import AuditLog, StudentGroupMembership

    group_a, group_b = _two_active_groups(db)
    student = attendance_service.get_active_students(db, group_a.id, DAY1)[0]

    r = client.patch(
        f"/admin/students/{student.id}", headers=admin_headers,
        json={"study_group_id": group_b.id},
    )
    assert r.status_code == 200, r.text

    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "student.group_transfer", AuditLog.entity_id == str(student.id))
        .one()
    )
    assert entry.old_value == str(group_a.id)
    assert entry.new_value == str(group_b.id)

    rows = (
        db.query(StudentGroupMembership)
        .filter(StudentGroupMembership.student_id == student.id)
        .order_by(StudentGroupMembership.start_date)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].study_group_id == group_a.id
    assert rows[0].end_date is not None
    assert rows[1].study_group_id == group_b.id
    assert rows[1].end_date is None


def test_no_transfer_when_group_unchanged(client, admin_headers, imported, db):
    """PATCH без реальной смены группы (или с другими полями) не должен
    плодить лишние строки членства."""
    from app.models import StudentGroupMembership

    group_a, _ = _two_active_groups(db)
    student = attendance_service.get_active_students(db, group_a.id, DAY1)[0]

    r = client.patch(
        f"/admin/students/{student.id}", headers=admin_headers,
        json={"study_group_id": group_a.id},
    )
    assert r.status_code == 200, r.text

    rows = db.query(StudentGroupMembership).filter(StudentGroupMembership.student_id == student.id).all()
    assert len(rows) == 1


def test_student_card_period_stats_unaffected_by_group(client, admin_headers, imported, db, curator_user):
    """Личная статистика студента (student_id=...) считает все его дни
    независимо от того, в какой группе он был в конкретный день."""
    group_a, group_b = _two_active_groups(db)
    student = attendance_service.get_active_students(db, group_a.id, DAY1)[0]

    attendance_service.submit_day(
        db, group_a.id, DAY1,
        [{"student_id": student.id, "mark_code": "н", "comment": None, "basis_reference": None}],
        curator_user, today=DAY1,
    )
    client.patch(f"/admin/students/{student.id}", headers=admin_headers, json={"study_group_id": group_b.id})
    db.commit()
    db.expire_all()

    stats = stats_service.compute_period_stats(db, DAY1, today_local(), student_id=student.id)
    assert stats.absent_unexcused == 1


def test_delete_student_after_transfer_without_marks_is_clean(client, admin_headers, imported, db):
    """Членство в группе само по себе не должно мешать чистому удалению —
    это не "история" в смысле раздела 1.1 (см. TODO.md 3), только отметки
    посещаемости настоящая причина обезличивать вместо удаления."""
    from app.models import StudentGroupMembership

    group_a, group_b = _two_active_groups(db)
    student = attendance_service.get_active_students(db, group_a.id, DAY1)[0]

    r = client.patch(f"/admin/students/{student.id}", headers=admin_headers, json={"study_group_id": group_b.id})
    assert r.status_code == 200, r.text
    assert db.query(StudentGroupMembership).filter(StudentGroupMembership.student_id == student.id).count() == 2

    client.patch(f"/admin/students/{student.id}", headers=admin_headers, json={"status": "expelled"})
    r = client.delete(f"/admin/students/{student.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert r.json()["anonymized"] is False

    assert db.query(StudentGroupMembership).filter(StudentGroupMembership.student_id == student.id).count() == 0
