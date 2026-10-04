"""Стирание персональных данных студента: досье, представители, заметки, ответы по задачам.

Вызывается везде, где студента удаляют или обезличивают: иначе FK из этих таблиц либо мешают
удалению (и студент «обезличивается» с телефонами и особыми данными), либо остаются висеть."""
from sqlalchemy.orm import Session

from app.models import (
    DossierAccessLog, StudentGuardian, StudentNote, StudentProfile, TaskComment, TaskRow,
)


def erase_student_personal_data(db: Session, student_ids: list[int], include_access_log: bool = False) -> None:
    """Удаляет данные досье и ответы по задачам. Журнал просмотров досье содержит только id
    и кто смотрел — при обезличивании (запись студента остаётся) его оставляем как след доступа;
    при полном удалении студента строки журнала удаляются: на них FK."""
    if not student_ids:
        return
    for start in range(0, len(student_ids), 500):
        chunk = student_ids[start:start + 500]
        db.query(TaskComment).filter(TaskComment.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(TaskRow).filter(TaskRow.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(StudentNote).filter(StudentNote.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(StudentGuardian).filter(StudentGuardian.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(StudentProfile).filter(StudentProfile.student_id.in_(chunk)).delete(synchronize_session=False)
        if include_access_log:
            db.query(DossierAccessLog).filter(DossierAccessLog.student_id.in_(chunk)).delete(synchronize_session=False)
