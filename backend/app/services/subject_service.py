from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import GroupSubject, User
from app.schemas.subjects import SubjectWrite


def list_subjects(db: Session, group_id: int) -> list[GroupSubject]:
    rows = db.query(GroupSubject).filter(GroupSubject.study_group_id == group_id).all()
    return sorted(rows, key=lambda s: s.name.casefold())


def _check_unique(db: Session, group_id: int, payload: SubjectWrite, own_id: int | None) -> None:
    for other in db.query(GroupSubject).filter(GroupSubject.study_group_id == group_id).all():
        if other.id == own_id:
            continue
        if other.name.casefold() == payload.name.casefold():
            raise HTTPException(status.HTTP_409_CONFLICT, "Такая дисциплина в группе уже есть")
        if payload.code and other.code and other.code.casefold() == payload.code.casefold():
            raise HTTPException(status.HTTP_409_CONFLICT, "Дисциплина с таким кодом в группе уже есть")


def _apply(row: GroupSubject, payload: SubjectWrite, user: User) -> None:
    row.code = payload.code
    row.name = payload.name
    row.teacher_name = payload.teacher_name
    row.teacher_phone = payload.teacher_phone
    row.note = payload.note
    row.updated_by_user_id = user.id


def create_subject(db: Session, group_id: int, payload: SubjectWrite, user: User) -> GroupSubject:
    _check_unique(db, group_id, payload, None)
    row = GroupSubject(study_group_id=group_id)
    _apply(row, payload, user)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_subject(db: Session, group_id: int, subject_id: int) -> GroupSubject:
    row = db.get(GroupSubject, subject_id)
    if row is None or row.study_group_id != group_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Дисциплина не найдена")
    return row


def update_subject(db: Session, group_id: int, subject_id: int, payload: SubjectWrite, user: User) -> GroupSubject:
    row = get_subject(db, group_id, subject_id)
    _check_unique(db, group_id, payload, row.id)
    _apply(row, payload, user)
    db.commit()
    db.refresh(row)
    return row


def delete_subject(db: Session, group_id: int, subject_id: int) -> None:
    db.delete(get_subject(db, group_id, subject_id))
    db.commit()
