"""Задачи от администрации (futures.md, этап 3): создание по охвату, заполнение
куратором, проверка, уведомления, прогресс, выгрузка.

Жизненный цикл назначения:
  new → in_progress (черновик) → submitted → accepted
                                     ↘ returned (с комментарием) → in_progress
«Просрочено» — признак поверх статуса: срок прошёл, а accepted нет.
Форма ответа и охват лежат JSON-ом в самой задаче."""
import datetime
import io
import json
import re
from typing import Any

from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy.orm import Session

from app.api.deps import DEPARTMENT_SCOPED_ROLES, get_curator_group_ids
from app.core.time import today_local, utcnow
from app.models import (
    CuratorAssignment, RoleCode, Student, StudyGroup, Task, TaskAssignment, TaskComment, TaskRow, User,
)
from app.schemas.tasks import FieldDef, Progress, ScopeDef, TaskCreate
from app.services import attendance_service, in_app_notification_service

TASK_MANAGER_ROLES = (RoleCode.ADMIN, RoleCode.EDU_DEPARTMENT, RoleCode.TUTOR, RoleCode.DEPT_HEAD)
EDITABLE_STATUSES = ("new", "in_progress", "returned")
STATUSES = ("new", "in_progress", "submitted", "returned", "accepted")


def is_manager(user: User) -> bool:
    return RoleCode(user.role.code) in TASK_MANAGER_ROLES


def _bad(message: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, message)


# ---------- форма ответа ----------

def normalize_fields(fields: list[FieldDef]) -> list[dict]:
    if not fields:
        raise _bad("Добавьте хотя бы одно поле формы")
    result, used = [], set()
    for i, f in enumerate(fields, start=1):
        key = re.sub(r"[^a-z0-9_]", "", (f.key or "").lower()) or f"f{i}"
        while key in used:
            key += "_"
        used.add(key)
        options = list(dict.fromkeys(o.strip() for o in f.options if o.strip()))
        if f.type in ("select", "multiselect") and not options:
            raise _bad(f"Поле «{f.label}»: укажите варианты выбора")
        result.append({
            "key": key, "label": f.label.strip(), "type": f.type, "required": f.required,
            "options": options if f.type in ("select", "multiselect") else [],
        })
    return result


def _is_empty(value) -> bool:
    return value is None or value == "" or value == []


def validate_value(field: dict, value: Any) -> Any:
    """Приводит значение к нормальному виду или бросает ValueError с понятным текстом."""
    if _is_empty(value):
        return None
    kind = field["type"]
    if kind == "text":
        text = str(value).strip()
        if len(text) > 2000:
            raise ValueError("слишком длинный текст (максимум 2000 символов)")
        return text or None
    if kind == "number":
        try:
            number = float(str(value).replace(",", "."))
        except ValueError:
            raise ValueError("нужно число")
        return int(number) if number.is_integer() else number
    if kind == "date":
        try:
            return datetime.date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise ValueError("нужна дата")
    if kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError("нужно да или нет")
    if kind == "select":
        if value not in field["options"]:
            raise ValueError("такого варианта нет в списке")
        return value
    if kind == "multiselect":
        if not isinstance(value, list) or any(v not in field["options"] for v in value):
            raise ValueError("выберите варианты из списка")
        return list(dict.fromkeys(value))
    if kind == "link":
        text = str(value).strip()
        if not re.match(r"^https?://\S+$", text) or len(text) > 500:
            raise ValueError("нужна ссылка вида https://…")
        return text
    raise ValueError("неизвестный тип поля")


def _clean_values(fields: list[dict], values: dict[str, Any]) -> dict[str, Any]:
    by_key = {f["key"]: f for f in fields}
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        field = by_key.get(key)
        if field is None:
            raise _bad(f"Неизвестное поле «{key}»")
        try:
            cleaned[key] = validate_value(field, value)
        except ValueError as exc:
            raise _bad(f"«{field['label']}»: {exc}")
    return {k: v for k, v in cleaned.items() if v is not None}


def _missing_required(fields: list[dict], values: dict[str, Any]) -> list[str]:
    return [f["label"] for f in fields if f["required"] and _is_empty(values.get(f["key"]))]


# ---------- охват ----------

def resolve_scope_groups(db: Session, scope: ScopeDef, creator: User) -> list[StudyGroup]:
    if not (scope.all_groups or scope.department_ids or scope.courses or scope.group_ids):
        raise _bad("Укажите охват: весь колледж, отделения, курсы или группы")
    groups = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).all()
    chosen = [
        g for g in groups
        if scope.all_groups or g.department_id in scope.department_ids or g.course in scope.courses
        or g.id in scope.group_ids
    ]
    chosen = [g for g in chosen if g.id not in scope.exclude_group_ids]
    if RoleCode(creator.role.code) in DEPARTMENT_SCOPED_ROLES:
        chosen = [g for g in chosen if g.department_id == creator.department_id]
    if not chosen:
        raise _bad("В охват не попала ни одна группа")
    return chosen


def create_task(db: Session, creator: User, payload: TaskCreate) -> Task:
    if payload.due_date < today_local():
        raise _bad("Срок не может быть в прошлом")
    fields = normalize_fields(payload.fields)
    groups = resolve_scope_groups(db, payload.scope, creator)
    task = Task(
        title=payload.title.strip(), description=(payload.description or "").strip() or None,
        created_by=creator.id, collect_mode=payload.collect_mode, reviewer_rule=payload.reviewer_rule,
        due_date=payload.due_date, fields_json=json.dumps(fields, ensure_ascii=False),
        scope_json=payload.scope.model_dump_json(),
    )
    db.add(task)
    db.flush()
    today = today_local()
    for g in groups:
        assignment = TaskAssignment(task_id=task.id, study_group_id=g.id, status="new")
        db.add(assignment)
        db.flush()
        for curator in assignees(db, g.id, today):
            in_app_notification_service.notify(
                db, curator, "task_assigned",
                f"Новая задача «{task.title}» для группы {g.code}, срок — {task.due_date.strftime('%d.%m.%Y')}.",
                entity_type="task_assignment", entity_id=str(assignment.id),
            )
    return task


def task_fields(task: Task) -> list[dict]:
    return json.loads(task.fields_json)


def assignees(db: Session, group_id: int, on_date: datetime.date) -> list[User]:
    rows = db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id == group_id).all()
    return [a.user for a in rows if a.is_active_on(on_date) and a.user.is_active]


# ---------- права ----------

def is_assignee(db: Session, user: User, assignment: TaskAssignment) -> bool:
    return assignment.study_group_id in get_curator_group_ids(db, user, today_local())


def can_review(user: User, assignment: TaskAssignment) -> bool:
    role = RoleCode(user.role.code)
    task = assignment.task
    if role == RoleCode.ADMIN:
        return True
    rule = task.reviewer_rule
    if rule == "dept_head":
        return role in DEPARTMENT_SCOPED_ROLES and user.department_id == assignment.study_group.department_id
    if rule == "edu_department":
        return role == RoleCode.EDU_DEPARTMENT
    if rule == "author":
        return user.id == task.created_by
    return False


def manager_sees(user: User, assignment: TaskAssignment) -> bool:
    """Управленческий просмотр: администратор и воспитательный отдел — всё, зав. отделением
    и тьютор — группы своего отделения, автор — свою задачу."""
    role = RoleCode(user.role.code)
    if role in (RoleCode.ADMIN, RoleCode.EDU_DEPARTMENT):
        return True
    if role in DEPARTMENT_SCOPED_ROLES and user.department_id == assignment.study_group.department_id:
        return True
    return user.id == assignment.task.created_by


def get_assignment_for(db: Session, user: User, assignment_id: int) -> TaskAssignment:
    assignment = db.get(TaskAssignment, assignment_id)
    if assignment is None:
        raise _bad("Назначение не найдено", status.HTTP_404_NOT_FOUND)
    if not (is_assignee(db, user, assignment) or can_review(user, assignment) or (is_manager(user) and manager_sees(user, assignment))):
        raise _bad("Нет доступа к этой задаче", status.HTTP_403_FORBIDDEN)
    return assignment


def is_overdue(assignment: TaskAssignment, today: datetime.date | None = None) -> bool:
    return assignment.status != "accepted" and assignment.task.due_date < (today or today_local())


# ---------- заполнение ----------

def _touch_in_progress(assignment: TaskAssignment) -> None:
    if assignment.status in ("new", "returned"):
        assignment.status = "in_progress"


def assert_editable(db: Session, user: User, assignment: TaskAssignment) -> None:
    if not is_assignee(db, user, assignment):
        raise _bad("Заполнять задачу может только куратор группы", status.HTTP_403_FORBIDDEN)
    if assignment.task.is_closed:
        raise _bad("Задача закрыта")
    if assignment.status not in EDITABLE_STATUSES:
        raise _bad("Ответ уже отправлен на проверку или принят — править нельзя")


def save_answers(db: Session, user: User, assignment: TaskAssignment, group_values: dict, rows: list) -> None:
    assert_editable(db, user, assignment)
    task = assignment.task
    fields = task_fields(task)
    if task.collect_mode == "group":
        if rows:
            raise _bad("В этой задаче ответ дают по группе, а не по студентам")
        assignment.group_values_json = json.dumps(_clean_values(fields, group_values), ensure_ascii=False)
    else:
        if group_values:
            raise _bad("В этой задаче ответ дают по студентам")
        roster = {s.id for s in attendance_service.get_active_students(db, assignment.study_group_id, today_local())}
        existing = {r.student_id: r for r in assignment.rows}
        for item in rows:
            if item.student_id not in roster:
                raise _bad("Студент не из этой группы")
            values = _clean_values(fields, item.values)
            included = True if task.collect_mode == "student" else item.is_included
            row = existing.get(item.student_id)
            if row is None:
                row = TaskRow(assignment_id=assignment.id, student_id=item.student_id)
                db.add(row)
                assignment.rows.append(row)
            row.is_included = included
            row.values_json = json.dumps(values if included else {}, ensure_ascii=False)
    _touch_in_progress(assignment)


def submit(db: Session, user: User, assignment: TaskAssignment) -> None:
    assert_editable(db, user, assignment)
    task = assignment.task
    fields = task_fields(task)
    problems: list[str] = []
    if task.collect_mode == "group":
        values = json.loads(assignment.group_values_json or "{}")
        problems = _missing_required(fields, values)
        if not any(not _is_empty(v) for v in values.values()) and not problems:
            problems = ["ответ не заполнен"]
    else:
        roster = attendance_service.get_active_students(db, assignment.study_group_id, today_local())
        rows = {r.student_id: r for r in assignment.rows}
        for s in roster:
            row = rows.get(s.id)
            if row is None:
                if task.collect_mode == "student":
                    problems.append(f"{s.full_name}: нет ответа")
                continue
            if row.is_included:
                missing = _missing_required(fields, json.loads(row.values_json))
                if missing:
                    problems.append(f"{s.full_name}: не заполнено — {', '.join(missing)}")
    if problems:
        shown = "; ".join(problems[:5]) + (f" … и ещё {len(problems) - 5}" if len(problems) > 5 else "")
        raise _bad(f"Нельзя отправить: {shown}")

    assignment.submitted_at = utcnow()
    assignment.review_comment = None
    if task.reviewer_rule == "none":
        assignment.status = "accepted"
        assignment.reviewed_at = utcnow()
        assignment.reviewed_by = None
        return
    assignment.status = "submitted"
    for reviewer in reviewers_to_notify(db, assignment):
        in_app_notification_service.notify(
            db, reviewer, "task_submitted",
            f"Группа {assignment.study_group.code} отправила на проверку задачу «{task.title}».",
            entity_type="task_assignment", entity_id=str(assignment.id),
        )


def reviewers_to_notify(db: Session, assignment: TaskAssignment) -> list[User]:
    task = assignment.task
    if task.reviewer_rule == "dept_head":
        dept = assignment.study_group.department_id
        return db.query(User).join(User.role).filter(
            User.is_active.is_(True), User.department_id == dept,
            User.role.has(code=RoleCode.DEPT_HEAD.value) | User.role.has(code=RoleCode.TUTOR.value),
        ).all()
    if task.reviewer_rule == "edu_department":
        return db.query(User).join(User.role).filter(
            User.is_active.is_(True), User.role.has(code=RoleCode.EDU_DEPARTMENT.value)
        ).all()
    if task.reviewer_rule == "author" and task.author is not None and task.author.is_active:
        return [task.author]
    return []


def review(db: Session, user: User, assignment: TaskAssignment, action: str, comment: str | None) -> None:
    if not can_review(user, assignment):
        raise _bad("Вы не проверяете эту задачу", status.HTTP_403_FORBIDDEN)
    if assignment.status != "submitted":
        raise _bad("Ответ не находится на проверке")
    comment = (comment or "").strip() or None
    if action == "return" and not comment:
        raise _bad("Напишите, что нужно доработать")
    assignment.status = "accepted" if action == "accept" else "returned"
    assignment.reviewed_by = user.id
    assignment.reviewed_at = utcnow()
    assignment.review_comment = comment
    if comment:
        db.add(TaskComment(assignment_id=assignment.id, author_id=user.id, text=comment))
    title = assignment.task.title
    verb = "принята" if action == "accept" else "возвращена на доработку"
    for curator in assignees(db, assignment.study_group_id, today_local()):
        in_app_notification_service.notify(
            db, curator, "task_accepted" if action == "accept" else "task_returned",
            f"Задача «{title}» для группы {assignment.study_group.code} {verb}." + (f" {comment}" if comment else ""),
            entity_type="task_assignment", entity_id=str(assignment.id),
        )


def add_comment(db: Session, user: User, assignment: TaskAssignment, student_id: int | None, text: str) -> TaskComment:
    if student_id is not None and db.get(Student, student_id) is None:
        raise _bad("Студент не найден")
    comment = TaskComment(assignment_id=assignment.id, student_id=student_id, author_id=user.id, text=text.strip())
    db.add(comment)
    # Ответить автору комментария — другой стороне: куратору, если пишет проверяющий, и наоборот.
    recipients = assignees(db, assignment.study_group_id, today_local()) if not is_assignee(db, user, assignment) \
        else reviewers_to_notify(db, assignment)
    for r in recipients:
        if r.id != user.id:
            in_app_notification_service.notify(
                db, r, "task_comment",
                f"Комментарий по задаче «{assignment.task.title}» (группа {assignment.study_group.code}): {comment.text[:200]}",
                entity_type="task_assignment", entity_id=str(assignment.id),
            )
    return comment


# ---------- прогресс и списки ----------

def progress(assignments: list[TaskAssignment], today: datetime.date | None = None) -> Progress:
    today = today or today_local()
    counts = {s: 0 for s in STATUSES}
    overdue = 0
    for a in assignments:
        counts[a.status] += 1
        overdue += is_overdue(a, today)
    return Progress(total=len(assignments), overdue=overdue, **counts)


def visible_assignments(db: Session, user: User, task: Task) -> list[TaskAssignment]:
    rows = (
        db.query(TaskAssignment).join(StudyGroup, StudyGroup.id == TaskAssignment.study_group_id)
        .filter(TaskAssignment.task_id == task.id).order_by(StudyGroup.course, StudyGroup.code).all()
    )
    return [a for a in rows if manager_sees(user, a)]


def manager_tasks(db: Session, user: User) -> list[tuple[Task, list[TaskAssignment]]]:
    result = []
    for task in db.query(Task).order_by(Task.due_date, Task.id.desc()).all():
        visible = visible_assignments(db, user, task)
        if visible or task.created_by == user.id:
            result.append((task, visible))
    return result


# ---------- выгрузка ----------

def export_workbook(db: Session, user: User, task: Task) -> bytes:
    fields = task_fields(task)
    assignments = visible_assignments(db, user, task)
    wb = Workbook()
    ws = wb.active
    ws.title = "Ответы"
    per_student = task.collect_mode != "group"
    head = ["Отделение", "Группа", "Статус"] + (["Студент"] if per_student else []) + [f["label"] for f in fields]
    head.append("Комментарий проверяющего")
    ws.append(head)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    status_ru = {"new": "Не начато", "in_progress": "В работе", "submitted": "На проверке",
                 "returned": "Возвращено", "accepted": "Принято"}

    def fmt(value) -> str:
        if isinstance(value, bool):
            return "да" if value else "нет"
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return "" if value is None else str(value)

    for a in assignments:
        base = [a.study_group.department.name, a.study_group.code, status_ru[a.status]]
        if not per_student:
            values = json.loads(a.group_values_json or "{}")
            ws.append(base + [fmt(values.get(f["key"])) for f in fields] + [a.review_comment or ""])
            continue
        names = {s.id: s.full_name for s in attendance_service.get_active_students(db, a.study_group_id, today_local())}
        for row in sorted(a.rows, key=lambda r: names.get(r.student_id, "")):
            if not row.is_included or row.student_id not in names:
                continue
            values = json.loads(row.values_json)
            ws.append(base + [names[row.student_id]] + [fmt(values.get(f["key"])) for f in fields] + [a.review_comment or ""])
    for idx in range(1, len(head) + 1):
        ws.column_dimensions[chr(64 + idx) if idx <= 26 else "AA"].width = 22
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
