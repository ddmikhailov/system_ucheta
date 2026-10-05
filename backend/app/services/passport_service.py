"""Социальный паспорт группы (этап 2): сводка из досье студентов —
сколько сирот, ОВЗ, многодетных и т. д., плюс заполненность досье.

Считаются студенты, числящиеся в группе на сегодня. Особые категории берутся из
зашифрованного блока досье; без ключа шифрования они недоступны (special_available=False),
остальные показатели (финансирование, возраст, заполненность) считаются всегда."""
import datetime
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core import field_crypto
from app.core.roles import COLLEGE_WIDE_ROLES, DEPARTMENT_SCOPED_ROLES
from app.core.time import today_local
from app.models import RoleCode, Student, StudentGroupMembership, StudentGuardian, StudentProfile, StudyGroup, User
from app.schemas.dossier import SpecialData
from app.services.access_service import get_curator_group_ids

# (ключ, название, функция по SpecialData)
CATEGORIES: list[tuple[str, str, callable]] = [
    ("orphan", "Сироты", lambda s: s.is_orphan),
    ("guardianship", "Под опекой", lambda s: s.under_guardianship),
    ("disability", "Инвалидность", lambda s: bool(s.disability_group)),
    ("ovz", "ОВЗ", lambda s: s.has_ovz),
    ("large_family", "Многодетные семьи", lambda s: s.large_family),
    ("low_income", "Малоимущие семьи", lambda s: s.low_income),
    ("pdn_kdn", "Учёт ПДН/КДН", lambda s: s.pdn_kdn),
    ("internal_record", "Внутренний учёт", lambda s: s.internal_record),
    ("scholarship", "Стипендия / соцвыплаты", lambda s: bool(s.scholarship)),
]
CATEGORY_TITLES = {key: title for key, title, _ in CATEGORIES}


@dataclass
class GroupPassport:
    group: StudyGroup
    students_total: int = 0
    minors: int = 0
    adults: int = 0
    birth_date_missing: int = 0
    budget: int = 0
    contract: int = 0
    funding_missing: int = 0
    no_guardians: int = 0
    dossier_empty: int = 0  # по студенту нет ни одного заполненного поля досье
    special_available: bool = True
    counts: dict[str, int] = field(default_factory=dict)
    names: dict[str, list[str]] = field(default_factory=dict)
    special_student_ids: set[int] = field(default_factory=set)  # чьи особые данные попали в паспорт


def accessible_groups(db: Session, user: User, department_id: int | None = None) -> list[StudyGroup]:
    """Группы, паспорт которых пользователь вправе видеть: куратор — свои, зав. отделением
    и тьютор — своего отделения, остальные (админ, воспитательный отдел, соц. педагог, психолог) — все."""
    today = today_local()
    role = RoleCode(user.role.code)
    q = db.query(StudyGroup).options(joinedload(StudyGroup.department)).filter(StudyGroup.is_active.is_(True))
    if role in DEPARTMENT_SCOPED_ROLES:
        q = q.filter(StudyGroup.department_id == user.department_id) if user.department_id is not None else q.filter(False)
    elif role in COLLEGE_WIDE_ROLES:
        pass
    else:
        ids = get_curator_group_ids(db, user, today)
        q = q.filter(StudyGroup.id.in_(ids)) if ids else q.filter(False)
    if department_id is not None:
        q = q.filter(StudyGroup.department_id == department_id)
    return q.order_by(StudyGroup.course, StudyGroup.code).all()


def build_passports(
    db: Session, groups: list[StudyGroup], today: datetime.date, with_names: bool
) -> list[GroupPassport]:
    """Паспорта сразу нескольких групп: число запросов не зависит от числа групп (состав групп,
    студенты, профили и представители грузятся по одному запросу на всю выборку)."""
    if not groups:
        return []
    group_ids = [g.id for g in groups]
    # Кто числится в группе сегодня — по истории членства, как в журнале посещаемости.
    member_rows = db.execute(
        select(StudentGroupMembership.study_group_id, StudentGroupMembership.student_id).where(
            StudentGroupMembership.study_group_id.in_(group_ids),
            StudentGroupMembership.start_date <= today,
            (StudentGroupMembership.end_date.is_(None)) | (StudentGroupMembership.end_date >= today),
        )
    ).all()
    student_ids = list({r.student_id for r in member_rows})
    students: dict[int, Student] = {}
    if student_ids:
        students = {
            s.id: s for s in db.execute(
                select(Student).where(
                    Student.id.in_(student_ids), Student.enrolled_at <= today,
                    (Student.left_at.is_(None)) | (Student.left_at >= today),
                )
            ).scalars()
        }
    by_group: dict[int, list[Student]] = {gid: [] for gid in group_ids}
    for r in member_rows:
        if r.student_id in students:
            by_group[r.study_group_id].append(students[r.student_id])
    for roster in by_group.values():
        roster.sort(key=lambda s: (s.last_name, s.first_name))

    profiles: dict[int, StudentProfile] = {}
    with_guardians: set[int] = set()
    if students:
        ids = list(students)
        profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(ids))}
        with_guardians = {
            row[0] for row in db.query(StudentGuardian.student_id).filter(StudentGuardian.student_id.in_(ids)).distinct()
        }
    encryption_ok = field_crypto.is_available()
    return [
        _passport_for(group, by_group[group.id], profiles, with_guardians, today, with_names, encryption_ok)
        for group in groups
    ]


def build_passport(db: Session, group: StudyGroup, today: datetime.date, with_names: bool) -> GroupPassport:
    return build_passports(db, [group], today, with_names)[0]


def _passport_for(
    group: StudyGroup, students: list[Student], profiles: dict[int, StudentProfile], with_guardians: set[int],
    today: datetime.date, with_names: bool, encryption_ok: bool,
) -> GroupPassport:
    result = GroupPassport(group=group, students_total=len(students), special_available=encryption_ok)
    result.counts = {key: 0 for key, _, _ in CATEGORIES}
    result.names = {key: [] for key, _, _ in CATEGORIES}

    for s in students:
        p = profiles.get(s.id)
        if p is None or p.birth_date is None:
            result.birth_date_missing += 1
        else:
            age = today.year - p.birth_date.year - ((today.month, today.day) < (p.birth_date.month, p.birth_date.day))
            if age < 18:
                result.minors += 1
            else:
                result.adults += 1
        funding = p.funding if p else None
        if funding == "budget":
            result.budget += 1
        elif funding == "contract":
            result.contract += 1
        else:
            result.funding_missing += 1
        if s.id not in with_guardians:
            result.no_guardians += 1
        filled = p is not None and any(
            getattr(p, f) for f in ("birth_date", "funding", "phone", "email", "messenger",
                                    "registration_address", "residence_address", "special_enc")
        )
        if not filled and s.id not in with_guardians:
            result.dossier_empty += 1

        if encryption_ok and p is not None and p.special_enc:
            try:
                special = SpecialData(**field_crypto.decrypt_json(p.special_enc))
            except field_crypto.EncryptionUnavailable:
                result.special_available = False
                continue
            for key, _, test in CATEGORIES:
                if test(special):
                    result.counts[key] += 1
                    result.special_student_ids.add(s.id)
                    if with_names:
                        result.names[key].append(s.full_name)
    if not result.special_available:
        result.counts = {key: None for key in result.counts}
        result.names = {key: [] for key in result.names}
    return result
