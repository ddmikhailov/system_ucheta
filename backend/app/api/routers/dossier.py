"""Досье студента (futures.md, этап 1): профиль, представители, заметки.

Доступ — как к карточке студента: куратор/заместитель — своих групп, зав.
отделением — своего отделения, воспитательный отдел/админ/тьютор — всех.
Каждое открытие досье пишется в журнал просмотров; особые поля шифруются
(app/core/field_crypto.py), журнал смотрят только admin/tutor."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_dept_editor
from app.api.routers.students import _get_accessible_student
from app.core import field_crypto
from app.db.session import get_db
from app.models import (
    DossierAccessLog,
    RoleCode,
    Student,
    StudentGuardian,
    StudentNote,
    StudentProfile,
    User,
)
from app.schemas.dossier import (
    AccessLogRead,
    DossierRead,
    GuardianIn,
    GuardianRead,
    NoteIn,
    NoteRead,
    ProfileFields,
    ProfileUpdate,
    SpecialData,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/students/{student_id}/dossier", tags=["dossier"])

_PROFILE_FIELDS = tuple(ProfileFields.model_fields)


def _student(db: Session, user: User, student_id: int) -> Student:
    return _get_accessible_student(db, user, student_id)


def _read_special(profile: StudentProfile | None) -> SpecialData | None:
    """None — особых данных нет или их нельзя расшифровать (нет ключа)."""
    if profile is None or not profile.special_enc:
        return SpecialData() if field_crypto.is_available() else None
    try:
        return SpecialData(**field_crypto.decrypt_json(profile.special_enc))
    except field_crypto.EncryptionUnavailable:
        return None


def _note_read(n: StudentNote, user: User) -> NoteRead:
    is_admin = RoleCode(user.role.code) in (RoleCode.ADMIN, RoleCode.TUTOR)
    return NoteRead(
        id=n.id, kind=n.kind, text=n.text, author_id=n.author_id,
        author_name=n.author.full_name if n.author else None, created_at=n.created_at,
        can_delete=is_admin or n.author_id == user.id,
    )


def _dossier(db: Session, user: User, student: Student) -> DossierRead:
    profile = db.get(StudentProfile, student.id)
    guardians = (
        db.query(StudentGuardian).filter(StudentGuardian.student_id == student.id)
        .order_by(StudentGuardian.is_primary.desc(), StudentGuardian.id).all()
    )
    notes = (
        db.query(StudentNote).filter(StudentNote.student_id == student.id)
        .order_by(StudentNote.created_at.desc(), StudentNote.id.desc()).all()
    )
    return DossierRead(
        student_id=student.id,
        profile=ProfileFields(**{f: getattr(profile, f, None) for f in _PROFILE_FIELDS}),
        special=_read_special(profile),
        special_available=field_crypto.is_available(),
        guardians=[GuardianRead(id=g.id, full_name=g.full_name, relation=g.relation, phone=g.phone,
                                is_primary=g.is_primary) for g in guardians],
        notes=[_note_read(n, user) for n in notes],
        can_edit=True,
    )


@router.get("", response_model=DossierRead)
def get_dossier(student_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    student = _student(db, user, student_id)
    result = _dossier(db, user, student)
    db.add(DossierAccessLog(student_id=student.id, user_id=user.id, included_special=result.special is not None))
    db.commit()
    return result


@router.put("/profile", response_model=DossierRead)
def update_profile(
    student_id: int, payload: ProfileUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _student(db, user, student_id)
    profile = db.get(StudentProfile, student.id)
    if profile is None:
        profile = StudentProfile(student_id=student.id)
        db.add(profile)

    changed = []
    for field in _PROFILE_FIELDS:
        value = getattr(payload, field)
        if isinstance(value, str):
            value = value.strip() or None
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed.append(field)

    if payload.special is not None:
        try:
            new_blob = field_crypto.encrypt_json(payload.special.model_dump())
            old = _read_special(profile) if profile.special_enc else SpecialData()
        except field_crypto.EncryptionUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Особые поля недоступны: {exc}")
        if old is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Особые поля недоступны: ключ не подходит")
        if old != payload.special:
            profile.special_enc = new_blob
            changed.append("special")

    if changed:
        # Значения не пишем в журнал: там ПДн, а особые — тем более. Только какие поля менялись.
        log_action(db, user, "dossier.profile_update", "student", str(student.id), new_value=",".join(changed))
    db.commit()
    return _dossier(db, user, student)


def _guardian(db: Session, student: Student, guardian_id: int) -> StudentGuardian:
    g = db.get(StudentGuardian, guardian_id)
    if g is None or g.student_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Представитель не найден")
    return g


def _apply_primary(db: Session, student_id: int, keep_id: int | None) -> None:
    q = db.query(StudentGuardian).filter(StudentGuardian.student_id == student_id)
    if keep_id is not None:
        q = q.filter(StudentGuardian.id != keep_id)
    q.update({StudentGuardian.is_primary: False})


@router.post("/guardians", response_model=GuardianRead, status_code=status.HTTP_201_CREATED)
def add_guardian(
    student_id: int, payload: GuardianIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _student(db, user, student_id)
    g = StudentGuardian(student_id=student.id, **payload.model_dump())
    db.add(g)
    db.flush()
    if g.is_primary:
        _apply_primary(db, student.id, g.id)
    log_action(db, user, "dossier.guardian_add", "student", str(student.id), new_value=str(g.id))
    db.commit()
    return GuardianRead(id=g.id, **payload.model_dump())


@router.put("/guardians/{guardian_id}", response_model=GuardianRead)
def update_guardian(
    student_id: int, guardian_id: int, payload: GuardianIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _student(db, user, student_id)
    g = _guardian(db, student, guardian_id)
    for k, v in payload.model_dump().items():
        setattr(g, k, v)
    if g.is_primary:
        _apply_primary(db, student.id, g.id)
    log_action(db, user, "dossier.guardian_update", "student", str(student.id), new_value=str(g.id))
    db.commit()
    return GuardianRead(id=g.id, **payload.model_dump())


@router.delete("/guardians/{guardian_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_guardian(
    student_id: int, guardian_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _student(db, user, student_id)
    g = _guardian(db, student, guardian_id)
    db.delete(g)
    log_action(db, user, "dossier.guardian_delete", "student", str(student.id), old_value=str(guardian_id))
    db.commit()


@router.post("/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def add_note(
    student_id: int, payload: NoteIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _student(db, user, student_id)
    note = StudentNote(student_id=student.id, author_id=user.id, kind=payload.kind, text=payload.text.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_read(note, user)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    student_id: int, note_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _student(db, user, student_id)
    note = db.get(StudentNote, note_id)
    if note is None or note.student_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заметка не найдена")
    if not _note_read(note, user).can_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Удалить заметку может только её автор или администратор")
    db.delete(note)
    log_action(db, user, "dossier.note_delete", "student", str(student.id), old_value=str(note_id))
    db.commit()


@router.get("/access-log", response_model=list[AccessLogRead])
def access_log(
    student_id: int, limit: int = 200,
    user: User = Depends(require_dept_editor), db: Session = Depends(get_db),
):
    _student(db, user, student_id)  # 404; у тьютора — 403 вне своего отделения
    rows = (
        db.query(DossierAccessLog).filter(DossierAccessLog.student_id == student_id)
        .order_by(DossierAccessLog.created_at.desc(), DossierAccessLog.id.desc())
        .limit(min(max(limit, 1), 1000)).all()
    )
    return [
        AccessLogRead(user_id=r.user_id, user_name=r.user.full_name, included_special=r.included_special,
                      created_at=r.created_at)
        for r in rows
    ]
