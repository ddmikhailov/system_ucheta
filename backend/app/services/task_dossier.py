"""Связь задач с досье (этап 4а): поле формы можно привязать к полю досье.

  * после ПРИЁМКИ значения по студентам записываются в досье (пустые ответы досье не стирают);
  * куратору форма открывается уже заполненной данными из досье (только для строк, которые он ещё не сохранял).

Привязать можно только «обычные» поля профиля. Особые категории (соц. статус, здоровье, учёт) сюда
намеренно не входят: они шифруются и видны узкому кругу, а ответы по задаче и их выгрузка видны шире.
Привязка возможна только в режимах «по каждому студенту» и «по выбранным» — у группового ответа нет студента."""
import datetime
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Student, StudentNote, StudentProfile, TaskAssignment, User
from app.schemas.dossier import ProfileFields
from app.services.audit_service import log_action

# ключ поля профиля → (название для людей, допустимые типы поля формы)
TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "phone": ("Телефон студента", ("text",)),
    "email": ("E-mail", ("text",)),
    "messenger": ("Мессенджер", ("text",)),
    "registration_address": ("Адрес регистрации", ("text",)),
    "residence_address": ("Адрес проживания", ("text",)),
    "birth_date": ("Дата рождения", ("date",)),
    "funding": ("Финансирование (бюджет/договор)", ("select",)),
    "additional_education": ("Дополнительное образование (кружки, секции)", ("text", "multiselect")),
}
FUNDING_LABELS = {"бюджет": "budget", "договор": "contract"}
FUNDING_BY_CODE = {code: label for label, code in FUNDING_LABELS.items()}


def targets_list() -> list[dict]:
    return [{"key": k, "label": label, "types": list(types)} for k, (label, types) in TARGETS.items()]


def validate_links(fields: list[dict], collect_mode: str) -> str | None:
    """Текст ошибки или None. Вызывается при создании задачи."""
    linked = [f for f in fields if f.get("dossier_field")]
    if not linked:
        return None
    if collect_mode == "group":
        return "Связать поле с досье можно только в задачах по студентам (ответ по группе не относится к студенту)"
    seen: set[str] = set()
    for f in linked:
        target = f["dossier_field"]
        if target not in TARGETS:
            return f"Поле «{f['label']}»: в досье нет поля «{target}» (особые данные к задачам не привязываются)"
        if f["type"] not in TARGETS[target][1]:
            return f"Поле «{f['label']}»: для «{TARGETS[target][0]}» подходит тип: {', '.join(TARGETS[target][1])}"
        if target in seen:
            return f"Два поля формы связаны с «{TARGETS[target][0]}»"
        seen.add(target)
        if target == "funding" and not set(f["options"]) <= set(FUNDING_LABELS):
            return f"Поле «{f['label']}»: варианты для финансирования — только «бюджет» и «договор»"
    return None


def max_length(target: str) -> int | None:
    for meta in ProfileFields.model_fields[target].metadata:
        limit = getattr(meta, "max_length", None)
        if limit is not None:
            return limit
    return None


def check_value(field: dict, value: Any) -> None:
    """Доп. проверка ответа в связанном поле: он должен влезть в поле досье (иначе ошибка выяснилась
    бы только при приёмке, когда куратор уже ничего не поправит)."""
    target = field.get("dossier_field")
    if not target or not isinstance(value, str):
        return
    limit = max_length(target)
    if limit is not None and len(value) > limit:
        raise ValueError(f"слишком длинное значение для поля досье (максимум {limit} символов)")


def _to_profile(target: str, value: Any) -> Any:
    if target == "birth_date":
        return datetime.date.fromisoformat(value)
    if target == "funding":
        return FUNDING_LABELS.get(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or None
    return str(value).strip() or None


def _to_form(target: str, value: Any, field: dict | None = None) -> Any:
    if value is None:
        return None
    if target == "birth_date":
        return value.isoformat()
    if target == "funding":
        return FUNDING_BY_CODE.get(value)
    if field is not None and field["type"] == "multiselect":
        # Подставляем, только если в досье ровно варианты формы: иначе сохранение формы затёрло бы
        # лишний текст, которого в вариантах нет.
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return parts if parts and all(p in field["options"] for p in parts) else None
    return value


def linked_fields(fields: list[dict]) -> list[dict]:
    return [f for f in fields if f.get("dossier_field") in TARGETS]


def prefill(db: Session, fields: list[dict], student_ids: list[int]) -> dict[int, dict[str, Any]]:
    """{student_id: {ключ поля формы: значение из досье}} — только непустые."""
    linked = linked_fields(fields)
    if not linked or not student_ids:
        return {}
    profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(student_ids))}
    result: dict[int, dict[str, Any]] = {}
    for sid, profile in profiles.items():
        values = {}
        for f in linked:
            value = _to_form(f["dossier_field"], getattr(profile, f["dossier_field"]), f)
            if value is not None and (f["type"] != "select" or value in f["options"]):
                values[f["key"]] = value
        if values:
            result[sid] = values
    return result


def apply_accepted(db: Session, actor: User, assignment: TaskAssignment, fields: list[dict]) -> int:
    """Записывает принятые ответы в досье. Возвращает число обновлённых студентов (без commit)."""
    linked = linked_fields(fields)
    if not linked:
        return 0
    task = assignment.task
    rows = [r for r in assignment.rows if r.is_included]
    if not rows:
        return 0
    ids = [r.student_id for r in rows]
    students = {s.id for s in db.query(Student.id).filter(Student.id.in_(ids))}
    profiles = {p.student_id: p for p in db.query(StudentProfile).filter(StudentProfile.student_id.in_(ids))}
    updated = 0
    for row in rows:
        if row.student_id not in students:
            continue
        values = json.loads(row.values_json)
        profile = profiles.get(row.student_id)
        changed: list[str] = []
        for f in linked:
            raw = values.get(f["key"])
            if raw is None or raw == "":
                continue  # пустое досье не стирает
            try:
                new = _to_profile(f["dossier_field"], raw)
            except ValueError:
                continue
            if new is None:
                continue
            if profile is None:
                profile = StudentProfile(student_id=row.student_id)
                db.add(profile)
                profiles[row.student_id] = profile
            if getattr(profile, f["dossier_field"]) != new:
                setattr(profile, f["dossier_field"], new)
                changed.append(f["dossier_field"])
        if changed:
            labels = ", ".join(TARGETS[c][0] for c in changed)
            # Значения не пишем ни в заметку, ни в журнал — там ПДн; только что и откуда обновилось.
            db.add(StudentNote(student_id=row.student_id, author_id=actor.id, kind="other",
                               text=f"Данные досье обновлены из задачи №{task.id} «{task.title}»: {labels}."))
            log_action(db, actor, "dossier.task_update", "student", str(row.student_id),
                       new_value=f"task:{task.id}:{','.join(changed)}")
            updated += 1
    return updated
