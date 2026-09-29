"""История членства студента в группе — какая группа отвечает за посещаемость
студента на конкретную дату, а не на текущий момент (см. TODO.md 3: раньше
перевод студента в другую группу задним числом переписывал всю его историю —
посещаемость до перевода начинала числиться за новой группой, а старая
группа теряла её из отчётов, потому что вся статистика смотрела на
`Student.study_group_id`, а это простой изменяемый FK без истории)."""
import datetime
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Student, StudentGroupMembership, User
from app.services.audit_service import log_action


def create_initial_membership(db: Session, student: Student) -> None:
    """Вызывается при создании студента — открывает членство в его группе
    с даты зачисления."""
    db.add(
        StudentGroupMembership(
            student_id=student.id, study_group_id=student.study_group_id,
            start_date=student.enrolled_at, end_date=None,
        )
    )


def transfer_student(
    db: Session, student: Student, new_group_id: int, effective_date: datetime.date, user: User
) -> None:
    """Закрывает текущее открытое членство и открывает новое — старая группа
    сохраняет всю историю до effective_date включительно, новая отвечает
    начиная с effective_date. Не трогает `student.study_group_id` — это
    делает вызывающий код (он же остаётся "текущей" группой для форм/списков)."""
    current = db.execute(
        select(StudentGroupMembership).where(
            StudentGroupMembership.student_id == student.id,
            StudentGroupMembership.end_date.is_(None),
        )
    ).scalar_one_or_none()
    if current is not None and current.study_group_id == new_group_id:
        return  # тот же самый group_id — не перевод, а, например, правка других полей
    if current is not None:
        current.end_date = effective_date - datetime.timedelta(days=1)
    db.add(
        StudentGroupMembership(
            student_id=student.id, study_group_id=new_group_id,
            start_date=effective_date, end_date=None,
        )
    )
    log_action(
        db, user, "student.group_transfer", "student", str(student.id),
        old_value=str(current.study_group_id) if current else None, new_value=str(new_group_id),
    )


def group_id_on(db: Session, student_id: int, date: datetime.date) -> int | None:
    """Группа, отвечавшая за студента на конкретную дату — одиночный запрос,
    не для горячих путей (см. `group_ids_on_bulk`/`membership_rows_by_student`
    для массовых расчётов)."""
    row = db.execute(
        select(StudentGroupMembership).where(
            StudentGroupMembership.student_id == student_id,
            StudentGroupMembership.start_date <= date,
        ).where(
            (StudentGroupMembership.end_date.is_(None)) | (StudentGroupMembership.end_date >= date)
        )
    ).scalar_one_or_none()
    return row.study_group_id if row else None


def membership_rows_by_student(
    db: Session, student_ids: list[int]
) -> dict[int, list[StudentGroupMembership]]:
    """Все строки членства нужных студентов, сгруппированные по student_id —
    основа для массового постраничного расчёта (день/период) без запроса на
    каждого студента по отдельности."""
    if not student_ids:
        return {}
    rows = db.execute(
        select(StudentGroupMembership).where(StudentGroupMembership.student_id.in_(student_ids))
    ).scalars().all()
    by_student: dict[int, list[StudentGroupMembership]] = defaultdict(list)
    for row in rows:
        by_student[row.student_id].append(row)
    return by_student


def resolve_group_id(rows: list[StudentGroupMembership], date: datetime.date) -> int | None:
    """То же, что `group_id_on`, но по уже загруженному списку строк — для
    цикла по многим датам/студентам без похода в БД на каждую пару."""
    for row in rows:
        if row.is_active_on(date):
            return row.study_group_id
    return None


def students_ever_in_group(
    db: Session, study_group_id: int, date_from: datetime.date, date_to: datetime.date
) -> set[int]:
    """id студентов, состоявших в этой группе хоть один день в диапазоне —
    включает и тех, кто уже перевёлся в другую группу, и тех, кто ещё не
    состоял (текущих участников тоже, раз FK совпадает с этим периодом).
    Без этого групповой отчёт за период молча терял студентов, переведённых
    из группы в середине периода (см. TODO.md 3)."""
    rows = db.execute(
        select(StudentGroupMembership.student_id).where(
            StudentGroupMembership.study_group_id == study_group_id,
            StudentGroupMembership.start_date <= date_to,
        ).where(
            (StudentGroupMembership.end_date.is_(None)) | (StudentGroupMembership.end_date >= date_from)
        )
    ).all()
    return {r.student_id for r in rows}
