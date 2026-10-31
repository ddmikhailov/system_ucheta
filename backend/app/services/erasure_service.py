"""Стирание персональных данных студента: досье, представители, заметки, ответы по задачам, отметки «Мой ID»,
присутствие на классных часах и родительских собраниях, комментарии «Восполнить пропуски».

Вызывается везде, где студента удаляют или обезличивают: иначе FK из этих таблиц либо мешают
удалению (и студент «обезличивается» с телефонами и особыми данными), либо остаются висеть."""
import json

from sqlalchemy.orm import Session

from app.models import (
    AbsenceCompensation, AbsencePeriod, AttendanceChangeRequest, AttendanceMark, DossierAccessLog, GroupEventAttendee, LessonMark,
    ParentMeetingAttendee, Student, StudentDeletionRequest, StudentGroupMembership, StudentGuardian, StudentMeal,
    StudentMyId, StudentNote, StudentProfile, TaskComment, TaskRow, User,
)
from app.services.audit_service import log_action, redact_audit_history


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
        db.query(StudentDeletionRequest).filter(StudentDeletionRequest.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(StudentMeal).filter(StudentMeal.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(StudentMyId).filter(StudentMyId.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(LessonMark).filter(LessonMark.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(AbsenceCompensation).filter(AbsenceCompensation.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(GroupEventAttendee).filter(GroupEventAttendee.student_id.in_(chunk)).delete(synchronize_session=False)
        guardian_ids = [g for (g,) in db.query(StudentGuardian.id).filter(StudentGuardian.student_id.in_(chunk))]
        if guardian_ids:
            db.query(ParentMeetingAttendee).filter(ParentMeetingAttendee.guardian_id.in_(guardian_ids)).delete(synchronize_session=False)
        db.query(StudentGuardian).filter(StudentGuardian.student_id.in_(chunk)).delete(synchronize_session=False)
        db.query(StudentProfile).filter(StudentProfile.student_id.in_(chunk)).delete(synchronize_session=False)
        if include_access_log:
            db.query(DossierAccessLog).filter(DossierAccessLog.student_id.in_(chunk)).delete(synchronize_session=False)


def _strip_from_change_requests(db: Session, student_id: int) -> None:
    """Запросы на правку дней хранят исключения JSON-ом без FK: убираем строки студента, чтобы одобрение
    запроса не упиралось в несуществующего студента, а его комментарии не пережили удаление."""
    for req in db.query(AttendanceChangeRequest).all():
        try:
            items = json.loads(req.exceptions_json)
        except ValueError:
            continue
        kept = [i for i in items if not (isinstance(i, dict) and i.get("student_id") == student_id)]
        if len(kept) != len(items):
            req.exceptions_json = json.dumps(kept, ensure_ascii=False)


def delete_student_completely(db: Session, user: User, student: Student) -> str:
    """Физическое удаление студента со всем, что на него ссылается: отметки посещаемости, длительные
    отсутствия, членство в группах, досье, ответы по задачам, присутствие на мероприятиях, журнал
    просмотров досье, ФИО в журнале действий. Необратимо; в отличие от обычного удаления не оставляет
    «Удалённый студент»."""
    student_id = student.id
    marks = db.query(AttendanceMark).filter(AttendanceMark.student_id == student_id).count()
    erase_student_personal_data(db, [student_id], include_access_log=True)
    db.query(AttendanceMark).filter(AttendanceMark.student_id == student_id).delete(synchronize_session=False)
    db.query(AbsencePeriod).filter(AbsencePeriod.student_id == student_id).delete(synchronize_session=False)
    db.query(StudentGroupMembership).filter(StudentGroupMembership.student_id == student_id).delete(synchronize_session=False)
    redact_audit_history(db, "student", str(student_id))
    _strip_from_change_requests(db, student_id)
    db.expire_all()
    db.delete(db.get(Student, student_id))
    log_action(db, user, "student.delete_cascade", "student", str(student_id), new_value=f"marks={marks}")
    db.commit()
    return f"Студент удалён навсегда вместе с историей (отметок посещаемости — {marks})"
