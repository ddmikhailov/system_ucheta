"""Карточка работы куратора (положение, п. 3.7): сводка по каждой группе за период — посещаемость, группа риска,
движение контингента и сданные дни. Только цифры, без общей оценки и рейтинга."""
import datetime
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Student, StudentGroupMembership
from app.models.enums import StudentStatus
from app.services import stats_service


def _contingent(db: Session, group_ids: list[int], date_from: datetime.date, date_to: datetime.date) -> dict[int, dict]:
    result = {gid: {"joined": 0, "left": 0, "transferred_in": 0, "transferred_out": 0, "academic_leave": 0} for gid in group_ids}
    if not group_ids:
        return result
    for s in db.execute(select(Student).where(Student.study_group_id.in_(group_ids))).scalars().all():
        row = result[s.study_group_id]
        if date_from <= s.enrolled_at <= date_to:
            row["joined"] += 1
        if s.status == StudentStatus.EXPELLED and s.left_at is not None and date_from <= s.left_at <= date_to:
            row["left"] += 1
        if s.status == StudentStatus.ACADEMIC_LEAVE:
            row["academic_leave"] += 1
    # Переводы — по истории членства: открытие нового членства не в день зачисления и закрытие старого при уходе в другую группу.
    memberships = db.execute(
        select(StudentGroupMembership, Student)
        .join(Student, Student.id == StudentGroupMembership.student_id)
        .where(StudentGroupMembership.study_group_id.in_(group_ids))
    ).all()
    for m, s in memberships:
        row = result[m.study_group_id]
        if date_from <= m.start_date <= date_to and m.start_date != s.enrolled_at:
            row["transferred_in"] += 1
        if m.end_date is not None and date_from <= m.end_date <= date_to and s.study_group_id != m.study_group_id:
            row["transferred_out"] += 1
    return result


def curator_cards(
    db: Session, date_from: datetime.date, date_to: datetime.date, department_id: int | None = None
) -> list[dict]:
    """Одна карточка на активную группу. Группа риска и «Восполнить пропуски» считаются с начала семестра по `date_to`
    (как везде в платформе), остальное — строго за период."""
    groups = stats_service._active_groups(db, department_id)
    if not groups:
        return []
    group_ids = [g.id for g in groups]
    discipline = {r["study_group_id"]: r for r in stats_service.curator_discipline(db, date_from, date_to, department_id)}
    flagged: dict[int, dict[str, int]] = defaultdict(lambda: {"risk": 0, "compensation": 0})
    for r in stats_service.risk_students(db, date_to, department_id):
        flagged[r["study_group_id"]][r["category"]] += 1
    active = defaultdict(int)
    for gid, status in db.execute(
        select(Student.study_group_id, Student.status).where(Student.study_group_id.in_(group_ids))
    ).all():
        if status == StudentStatus.STUDYING:
            active[gid] += 1
    contingent = _contingent(db, group_ids, date_from, date_to)

    cards = []
    for group in groups:
        stats = stats_service.compute_period_stats(db, date_from, date_to, study_group_id=group.id, only_submitted=True)
        d = discipline[group.id]
        cards.append(
            {
                "study_group_id": group.id,
                "code": group.code,
                "course": group.course,
                "department_id": group.department_id,
                "responsible_name": d["responsible_name"],
                "students_count": active[group.id],
                "attendance_percent": stats.percent if stats.in_list else None,
                "absent_unexcused_percent": round(stats.absent_unexcused / stats.in_list * 100, 1) if stats.in_list else None,
                "risk_count": flagged[group.id]["risk"],
                "compensation_count": flagged[group.id]["compensation"],
                "contingent": contingent[group.id],
                "on_time": d["on_time"],
                "late": d["late"],
                "missed": d["missed"],
                "total_study_days": d["total_study_days"],
            }
        )
    return cards
