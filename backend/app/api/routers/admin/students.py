"""Студенты: список, создание, статус, правка, удаление/обезличивание."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    require_dept_editor,
    require_management,
    require_structure_editor,
    scope_department_id,
)
from app.core import policies
from app.core.roles import is_department_scoped
from app.core.time import today_local
from app.db.session import get_db
from app.models import AttendanceMark, Student, StudentGroupMembership, StudentStatus, StudyGroup, User
from app.schemas.admin import DeleteResult, StudentCreate, StudentRead, StudentUpdate, StudentUpdateStatus
from app.services import group_membership_service
from app.services.erasure_service import erase_student_personal_data
from app.services.audit_service import log_action, redact_audit_history

router = APIRouter()


@router.get("/students", response_model=list[StudentRead])
def list_students(
    study_group_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    q = db.query(Student)
    if study_group_id is not None:
        q = q.filter(Student.study_group_id == study_group_id)
    if is_department_scoped(user):
        q = q.join(StudyGroup, StudyGroup.id == Student.study_group_id).filter(
            StudyGroup.department_id == scope_department_id(user, None)
        )
    students = q.order_by(Student.last_name, Student.first_name).all()
    return [_student_read(s) for s in students]


def _student_read(s: Student) -> StudentRead:
    # Раньше отдавался только full_name, склеенный на бэкенде — фронт
    # (StudentsTab.tsx) разбирал его обратно по пробелам для формы
    # редактирования, что ломается на составных фамилиях/именах (см.
    # TODO.md 5). Теперь части ФИО приходят отдельными полями напрямую
    # из БД, full_name остаётся для отображения в таблицах как было.
    return StudentRead(
        id=s.id, full_name=s.full_name,
        last_name=s.last_name, first_name=s.first_name, middle_name=s.middle_name,
        study_group_id=s.study_group_id, status=s.status, enrolled_at=s.enrolled_at, left_at=s.left_at,
    )




@router.post("/students", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate, user: User = Depends(require_dept_editor), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, payload.study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    policies.assert_can_manage_group(user, group)
    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    group_membership_service.create_initial_membership(db, student)
    log_action(db, user, "student.create", "student", str(student.id), new_value=student.full_name)
    db.commit()
    return _student_read(student)


@router.patch("/students/{student_id}/status", response_model=StudentRead)
def update_student_status(
    student_id: int, payload: StudentUpdateStatus,
    user: User = Depends(require_structure_editor), db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    policies.assert_can_manage_student(db, user, student)
    new_status = StudentStatus(payload.status)
    student.status = new_status
    if payload.left_at is not None:
        student.left_at = payload.left_at
    elif new_status == StudentStatus.STUDYING:
        # Возврат из академа/восстановление — дата выбытия больше не
        # актуальна, иначе студент продолжает считаться выбывшим и
        # пропадает из активного списка группы (см. TODO.md 3).
        student.left_at = None
    log_action(db, user, "student.status_change", "student", str(student.id))
    db.commit()
    db.refresh(student)
    return _student_read(student)


@router.patch("/students/{student_id}", response_model=StudentRead)
def update_student(
    student_id: int, payload: StudentUpdate,
    user: User = Depends(require_structure_editor), db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    policies.assert_can_manage_student(db, user, student)

    data = payload.model_dump(exclude_unset=True)
    is_group_transfer = "study_group_id" in data and data["study_group_id"] is not None and data["study_group_id"] != student.study_group_id
    if "study_group_id" in data and data["study_group_id"] is not None:
        target_group = db.get(StudyGroup, data["study_group_id"])
        if target_group is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Группа назначения не найдена")
        policies.assert_can_manage_group(user, target_group)
    if "status" in data and data["status"] is not None:
        data["status"] = StudentStatus(data["status"])

    new_group_id = data.get("study_group_id")
    for field, value in data.items():
        setattr(student, field, value)
    if is_group_transfer:
        # Перевод в другую группу переводит его дальше вперёд, но не
        # переписывает историю посещаемости в старой группе задним числом
        # (см. TODO.md 3) — старый FK Student.study_group_id остаётся для
        # форм/списков "текущая группа", а кто отвечал за какой день —
        # смотрит student_group_memberships.
        group_membership_service.transfer_student(db, student, new_group_id, today_local(), user)
    log_action(db, user, "student.update", "student", str(student.id))
    db.commit()
    db.refresh(student)
    return _student_read(student)


@router.delete("/students/{student_id}", response_model=DeleteResult)
def delete_student(
    student_id: int,
    user: User = Depends(require_structure_editor), db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    policies.assert_can_manage_student(db, user, student)
    if student.status == StudentStatus.STUDYING:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Сначала переведите студента в академ. отпуск или отчислите — удалить можно только архивного",
        )

    # Членство в группе само по себе не «история» в смысле этой проверки —
    # это просто учётная запись "кто где состоял", у неё нет собственной
    # ценности без отметок посещаемости. Без явного удаления здесь FK на
    # student_group_memberships (она есть у каждого студента после раздела 3)
    # обезличивал бы вообще всех студентов вместо чистого удаления.
    db.query(StudentGroupMembership).filter(StudentGroupMembership.student_id == student_id).delete()
    erase_student_personal_data(db, [student_id], include_access_log=True)

    try:
        db.delete(student)
        db.flush()
    except IntegrityError:
        db.rollback()
        # Откат вернул и досье — но студента при этом не удаляют, а обезличивают: его телефоны,
        # представители, заметки и особые данные должны исчезнуть так же, как ФИО.
        erase_student_personal_data(db, [student_id])
        # Есть отметки посещаемости — вместо удаления обезличиваем, чтобы не
        # потерять статистику и историю группы (обновление 1.1: удаление не
        # должно ломать базу и терять уже собранные данные).
        student.last_name = "Удалённый"
        student.first_name = "студент"
        student.middle_name = None
        # Раньше обезличивание останавливалось на ФИО студента — свободный
        # текст в комментариях/основаниях отметок (куратор мог написать,
        # например, "Иванов заболел, справка приложена") и старые записи
        # audit_log, где ещё сохранилось настоящее ФИО (см. student.create
        # ниже), по-прежнему выдавали личность (см. TODO.md 5).
        db.query(AttendanceMark).filter(AttendanceMark.student_id == student_id).update(
            {"comment": None, "basis_reference": None}, synchronize_session=False
        )
        redact_audit_history(db, "student", str(student_id))
        log_action(db, user, "student.anonymize", "student", str(student_id))
        db.commit()
        return DeleteResult(
            deleted=False, anonymized=True,
            detail="У студента есть история посещаемости — данные обезличены, запись оставлена в архиве",
        )

    log_action(db, user, "student.delete", "student", str(student_id))
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Студент удалён")
