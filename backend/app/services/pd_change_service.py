"""Изменения ПДн студентов за месяц — список для администратора, который сообщает о них в отдел кадров (п. 3.1.15).
Строится из журнала действий: значения в нём не хранятся, только названия изменённых полей."""
import datetime

from sqlalchemy.orm import Session

from app.models import AuditLog, Student, StudyGroup, User
from app.schemas.admin import PdChangeRead

NAME_FIELDS = {"last_name": "фамилия", "first_name": "имя", "middle_name": "отчество"}
PROFILE_FIELDS = {
    "birth_date": "дата рождения", "gender": "пол", "phone": "телефон", "email": "email", "messenger": "мессенджер",
    "registration_address": "адрес регистрации", "residence_address": "адрес проживания", "birth_place": "место рождения",
    "previous_education": "предыдущее образование", "enrollment_order": "приказ о зачислении", "special": "особые данные",
    "funding": "форма финансирования", "additional_education": "доп. образование",
}
GUARDIAN_ACTIONS = {
    "dossier.guardian_add": "добавлен законный представитель",
    "dossier.guardian_update": "изменён законный представитель",
    "dossier.guardian_delete": "удалён законный представитель",
}
ACTIONS = ("student.update", "dossier.profile_update", *GUARDIAN_ACTIONS)


def _fields(entry: AuditLog) -> list[str]:
    """Что изменилось в человеческих словах; пусто — запись не про ПДн (например, только смена группы или статуса)."""
    if entry.action in GUARDIAN_ACTIONS:
        return [GUARDIAN_ACTIONS[entry.action]]
    labels = NAME_FIELDS if entry.action == "student.update" else PROFILE_FIELDS
    return [labels[f] for f in (entry.new_value or "").split(",") if f in labels]


def month_bounds(month: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start = datetime.datetime.combine(month.replace(day=1), datetime.time.min)
    end = datetime.datetime.combine((start + datetime.timedelta(days=32)).replace(day=1), datetime.time.min)
    return start, end


def list_changes(db: Session, month: datetime.date) -> list[PdChangeRead]:
    start, end = month_bounds(month)
    entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "student", AuditLog.action.in_(ACTIONS), AuditLog.created_at >= start, AuditLog.created_at < end)
        .order_by(AuditLog.id.desc())
        .all()
    )
    students = {s.id: s for s in db.query(Student).filter(Student.id.in_({int(e.entity_id) for e in entries}))} if entries else {}
    groups = {g.id: g.code for g in db.query(StudyGroup)}
    users = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({e.user_id for e in entries if e.user_id}))} if entries else {}
    result = []
    for entry in entries:
        student = students.get(int(entry.entity_id))
        fields = _fields(entry)
        if student is None or not fields:
            continue
        result.append(PdChangeRead(
            created_at=entry.created_at, student_id=student.id, student_name=student.full_name,
            group_code=groups.get(student.study_group_id, ""), changed_by_name=users.get(entry.user_id),
            changes=fields,
        ))
    return result
