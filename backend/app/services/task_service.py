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
import time
from typing import Any

from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy.orm import Session, joinedload

from app.core.roles import DEPARTMENT_SCOPED_ROLES
from app.core.time import today_local, utcnow
from app.core.xlsx import append_row
from app.models import (
    AuditLog, CuratorAssignment, InAppNotification, RoleCode, Student, StudyGroup, Task, TaskAssignment, TaskComment, TaskRow, TaskTemplate, User,
)
from app.schemas.tasks import FieldDef, Progress, ScopeDef, TaskCreate
from app.services import attendance_service, in_app_notification_service, task_dossier
from app.services.access_service import get_curator_group_ids

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
            "dossier_field": f.dossier_field or None,
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
            task_dossier.check_value(field, cleaned[key])
        except ValueError as exc:
            raise _bad(f"«{field['label']}»: {exc}")
    return {k: v for k, v in cleaned.items() if v is not None}


def _missing_required(fields: list[dict], values: dict[str, Any]) -> list[str]:
    return [f["label"] for f in fields if f["required"] and _is_empty(values.get(f["key"]))]


# ---------- охват ----------

def scope_matches(scope: ScopeDef, group: StudyGroup) -> bool:
    if group.id in scope.exclude_group_ids:
        return False
    return (
        scope.all_groups or group.department_id in scope.department_ids or group.course in scope.courses
        or group.id in scope.group_ids
    )


def resolve_scope_groups(db: Session, scope: ScopeDef, creator: User) -> list[StudyGroup]:
    if not (scope.all_groups or scope.department_ids or scope.courses or scope.group_ids):
        raise _bad("Укажите охват: весь колледж, отделения, курсы или группы")
    groups = db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).all()
    chosen = [g for g in groups if scope_matches(scope, g)]
    if RoleCode(creator.role.code) in DEPARTMENT_SCOPED_ROLES:
        chosen = [g for g in chosen if g.department_id == creator.department_id]
    if not chosen:
        raise _bad("В охват не попала ни одна группа")
    return chosen


def create_task(db: Session, creator: User, payload: TaskCreate) -> Task:
    if payload.due_date < today_local():
        raise _bad("Срок не может быть в прошлом")
    fields = normalize_fields(payload.fields)
    link_error = task_dossier.validate_links(fields, payload.collect_mode)
    if link_error:
        raise _bad(link_error)
    prev = None
    if payload.after_task_id is not None:
        prev = _step_predecessor(db, creator, payload)
        scope = ScopeDef(**json.loads(prev.scope_json))
        groups = [a.study_group for a in prev.assignments if a.study_group.is_active]
        if not groups:
            raise _bad("В предыдущем шаге нет активных групп")
    else:
        scope = payload.scope
        groups = resolve_scope_groups(db, scope, creator)
    task = Task(
        title=payload.title.strip(), description=(payload.description or "").strip() or None,
        created_by=creator.id, collect_mode=payload.collect_mode, reviewer_rule=payload.reviewer_rule,
        due_date=payload.due_date, fields_json=json.dumps(fields, ensure_ascii=False),
        scope_json=scope.model_dump_json(),
    )
    if prev is not None:
        if prev.series_id is None:
            prev.series_id = prev.id
        task.series_id, task.step_no, task.unlock_on = prev.series_id, prev.step_no + 1, payload.unlock_on
    db.add(task)
    db.flush()
    today = today_local()
    prev_by_group = {a.study_group_id: a for a in prev.assignments} if prev is not None else {}
    for g in groups:
        before = prev_by_group.get(g.id)
        locked = before is not None and not step_is_open(before, payload.unlock_on)
        assignment = TaskAssignment(task_id=task.id, study_group_id=g.id, status="new", locked=locked)
        db.add(assignment)
        db.flush()
        for curator in ([] if locked else assignees(db, g.id, today)):
            in_app_notification_service.notify(
                db, curator, "task_assigned",
                f"Новая задача «{task.title}» для группы {g.code}, срок — {task.due_date.strftime('%d.%m.%Y')}.",
                entity_type="task_assignment", entity_id=str(assignment.id),
            )
    return task


# ---------- многошаговые задачи ----------

def step_is_open(previous: TaskAssignment, unlock_on: str | None) -> bool:
    """Следующий шаг открыт, если предыдущий принят, а при правиле «после сдачи» — достаточно и сдачи."""
    return previous.status == "accepted" or (unlock_on == "submitted" and previous.status == "submitted")


def _step_predecessor(db: Session, creator: User, payload: TaskCreate) -> Task:
    prev = db.get(Task, payload.after_task_id)
    if prev is None:
        raise _bad("Предыдущий шаг не найден", status.HTTP_404_NOT_FOUND)
    if RoleCode(creator.role.code) != RoleCode.ADMIN and prev.created_by != creator.id:
        raise _bad("Добавлять шаги может автор задачи или администратор", status.HTTP_403_FORBIDDEN)
    if prev.series_id is not None and db.query(Task.id).filter(
        Task.series_id == prev.series_id, Task.step_no == prev.step_no + 1
    ).first():
        raise _bad("После этого шага уже есть следующий — добавляйте шаг после последнего")
    if payload.due_date < prev.due_date:
        raise _bad("Срок шага не может быть раньше срока предыдущего шага")
    return prev


def next_step(db: Session, task: Task) -> Task | None:
    if task.series_id is None:
        return None
    return db.query(Task).filter(Task.series_id == task.series_id, Task.step_no == task.step_no + 1).first()


def series_steps(db: Session, task: Task) -> list[Task]:
    if task.series_id is None:
        return []
    steps = db.query(Task).filter(Task.series_id == task.series_id).order_by(Task.step_no).all()
    return steps if len(steps) > 1 else []


def lock_reason(db: Session, assignment: TaskAssignment) -> str | None:
    if not assignment.locked:
        return None
    task = assignment.task
    prev = db.query(Task).filter(Task.series_id == task.series_id, Task.step_no == task.step_no - 1).first()
    when = "сдан" if task.unlock_on == "submitted" else "принят"
    return f"Этот шаг откроется, когда предыдущий шаг «{prev.title if prev else '…'}» будет {when}."


def unlock_next_step(db: Session, assignment: TaskAssignment) -> None:
    """Вызывается, когда назначение сдано или принято: открывает следующий шаг этой же группы."""
    nxt = next_step(db, assignment.task)
    if nxt is None:
        return
    target = db.query(TaskAssignment).filter(
        TaskAssignment.task_id == nxt.id, TaskAssignment.study_group_id == assignment.study_group_id
    ).first()
    if target is None or not target.locked or not step_is_open(assignment, nxt.unlock_on):
        return
    target.locked = False
    for curator in assignees(db, assignment.study_group_id, today_local()):
        in_app_notification_service.notify(
            db, curator, "task_assigned",
            f"Открыт следующий шаг «{nxt.title}» для группы {assignment.study_group.code}, срок — {_fmt(nxt.due_date)}.",
            entity_type="task_assignment", entity_id=str(target.id),
        )


def template_from_task(task: Task, user: User, name: str | None) -> TaskTemplate:
    """Шаблон = задача без срока. Форма и охват берутся как сохранены (поля уже нормализованы)."""
    payload = {
        "title": task.title, "description": task.description, "collect_mode": task.collect_mode,
        "reviewer_rule": task.reviewer_rule, "fields": json.loads(task.fields_json), "scope": json.loads(task.scope_json),
    }
    return TaskTemplate(
        name=(name or "").strip() or task.title, created_by=user.id, payload_json=json.dumps(payload, ensure_ascii=False),
    )


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
    if rule == "two_step":
        if assignment.review_step == 1:
            return role in DEPARTMENT_SCOPED_ROLES and user.department_id == assignment.study_group.department_id
        return role == RoleCode.EDU_DEPARTMENT
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
    return assignment.status != "accepted" and not assignment.locked and assignment.task.due_date < (today or today_local())


# ---------- заполнение ----------

def _touch_in_progress(assignment: TaskAssignment) -> None:
    if assignment.status in ("new", "returned"):
        assignment.status = "in_progress"


def assert_editable(db: Session, user: User, assignment: TaskAssignment) -> None:
    if not is_assignee(db, user, assignment):
        raise _bad("Заполнять задачу может только куратор группы", status.HTTP_403_FORBIDDEN)
    if assignment.task.is_closed:
        raise _bad("Задача закрыта")
    if assignment.locked:
        raise _bad(lock_reason(db, assignment) or "Шаг ещё закрыт")
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
    assignment.review_step = 1
    if task.reviewer_rule == "none":
        assignment.status = "accepted"
        assignment.reviewed_at = utcnow()
        assignment.reviewed_by = None
        task_dossier.apply_accepted(db, user, assignment, fields)
        unlock_next_step(db, assignment)
        return
    assignment.status = "submitted"
    unlock_next_step(db, assignment)  # шаги с правилом «после сдачи» открываются сразу
    for reviewer in reviewers_to_notify(db, assignment):
        in_app_notification_service.notify(
            db, reviewer, "task_submitted",
            f"Группа {assignment.study_group.code} отправила на проверку задачу «{task.title}».",
            entity_type="task_assignment", entity_id=str(assignment.id),
        )


def reviewers_to_notify(db: Session, assignment: TaskAssignment) -> list[User]:
    task = assignment.task
    if task.reviewer_rule == "dept_head" or (task.reviewer_rule == "two_step" and assignment.review_step == 1):
        dept = assignment.study_group.department_id
        return db.query(User).join(User.role).filter(
            User.is_active.is_(True), User.department_id == dept,
            User.role.has(code=RoleCode.DEPT_HEAD.value) | User.role.has(code=RoleCode.TUTOR.value),
        ).all()
    if task.reviewer_rule == "edu_department" or (task.reviewer_rule == "two_step" and assignment.review_step == 2):
        return db.query(User).join(User.role).filter(
            User.is_active.is_(True), User.role.has(code=RoleCode.EDU_DEPARTMENT.value)
        ).all()
    if task.reviewer_rule == "author" and task.author is not None and task.author.is_active:
        return [task.author]
    return []


def assignment_history(db: Session, assignment: TaskAssignment) -> list[dict]:
    """Ход проверки по журналу аудита: кто и когда отправил, принял (на какой ступени) или вернул.
    Отдельной таблицы не нужно — каждое действие уже пишется в audit_log."""
    rows = (
        db.query(AuditLog).options(joinedload(AuditLog.user))
        .filter(
            AuditLog.entity_type == "task_assignment", AuditLog.entity_id == str(assignment.id),
            AuditLog.action.in_(("task.submit", "task.accept", "task.return")),
        )
        .order_by(AuditLog.created_at, AuditLog.id).all()
    )
    kinds = {"task.submit": "submitted", "task.accept": "accepted", "task.return": "returned"}
    events = []
    for r in rows:
        step = None
        if r.new_value and r.new_value.startswith("step:") and assignment.task.reviewer_rule == "two_step":
            step = int(r.new_value.split(":", 1)[1])
        events.append({
            "kind": kinds[r.action], "user_name": r.user.full_name if r.user else None,
            "at": r.created_at, "step": step,
        })
    if assignment.status == "accepted" and assignment.task.reviewer_rule == "none" and assignment.reviewed_at:
        events.append({"kind": "auto_accepted", "user_name": None, "at": assignment.reviewed_at, "step": None})
    return events


def review(db: Session, user: User, assignment: TaskAssignment, action: str, comment: str | None) -> None:
    if not can_review(user, assignment):
        raise _bad("Вы не проверяете эту задачу", status.HTTP_403_FORBIDDEN)
    if assignment.status != "submitted":
        raise _bad("Ответ не находится на проверке")
    comment = (comment or "").strip() or None
    if action == "return" and not comment:
        raise _bad("Напишите, что нужно доработать")
    if action == "accept" and assignment.task.reviewer_rule == "two_step" and assignment.review_step == 1:
        # Первая ступень пройдена — дальше воспитательный отдел; куратору пока ничего не сообщаем.
        assignment.review_step = 2
        if comment:
            db.add(TaskComment(assignment_id=assignment.id, author_id=user.id, text=comment))
        for reviewer in reviewers_to_notify(db, assignment):
            in_app_notification_service.notify(
                db, reviewer, "task_submitted",
                f"Задача «{assignment.task.title}», группа {assignment.study_group.code}: "
                "зав. отделением принял(а), ждёт вашей проверки.",
                entity_type="task_assignment", entity_id=str(assignment.id),
            )
        return
    assignment.review_step = 1
    assignment.status = "accepted" if action == "accept" else "returned"
    assignment.reviewed_by = user.id
    assignment.reviewed_at = utcnow()
    assignment.review_comment = comment
    if comment:
        db.add(TaskComment(assignment_id=assignment.id, author_id=user.id, text=comment))
    if action == "accept":
        task_dossier.apply_accepted(db, user, assignment, task_fields(assignment.task))
        unlock_next_step(db, assignment)
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
        .options(joinedload(TaskAssignment.study_group).joinedload(StudyGroup.department),
                 joinedload(TaskAssignment.task), joinedload(TaskAssignment.reviewer))
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
    append_row(ws, head)
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
            append_row(ws, base + [fmt(values.get(f["key"])) for f in fields] + [a.review_comment or ""])
            continue
        names = {s.id: s.full_name for s in attendance_service.get_active_students(db, a.study_group_id, today_local())}
        for row in sorted(a.rows, key=lambda r: names.get(r.student_id, "")):
            if not row.is_included or row.student_id not in names:
                continue
            values = json.loads(row.values_json)
            append_row(ws, base + [names[row.student_id]] + [fmt(values.get(f["key"])) for f in fields] + [a.review_comment or ""])
    for idx in range(1, len(head) + 1):
        ws.column_dimensions[chr(64 + idx) if idx <= 26 else "AA"].width = 22
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- напоминания о сроках ----------
# Отдельного планировщика нет: сроки проверяются при открытии платформы (колокольчик
# опрашивает /notifications/unread-count при входе и раз в минуту). Каждое напоминание
# создаётся один раз на (пользователь, назначение, вид); проверка не чаще раза в 10 минут.

REMIND_DAYS_BEFORE = 3
REVIEW_WAIT_DAYS = 2
REMINDER_THROTTLE_SECONDS = 600
DEADLINE_REMINDER_KINDS = ("task_due_soon", "task_due_today", "task_overdue")
REMINDER_KINDS = (*DEADLINE_REMINDER_KINDS, "task_review_waiting")
_last_reminder_run: dict[int, float] = {}


def reset_reminder_throttle() -> None:
    from app.services import task_schedule

    task_schedule.reset_throttle()
    _last_reminder_run.clear()


def _fmt(d: datetime.date) -> str:
    return d.strftime("%d.%m.%Y")


def reset_deadline_reminders(db: Session, task: Task) -> int:
    """Срок задачи изменили — прежние напоминания о сроках устарели («срок был …») и, главное, мешают
    выдать новые: каждое приходит один раз на назначение. Удаляем их, чтобы цикл начался заново
    (без commit). «Ждёт проверки» от срока не зависит и остаётся."""
    ids = [str(a.id) for a in task.assignments]
    if not ids:
        return 0
    return db.query(InAppNotification).filter(
        InAppNotification.entity_type == "task_assignment", InAppNotification.entity_id.in_(ids),
        InAppNotification.kind.in_(DEADLINE_REMINDER_KINDS),
    ).delete(synchronize_session=False)


def generate_reminders(db: Session, user: User, today: datetime.date | None = None, force: bool = False) -> int:
    """Создаёт недостающие напоминания пользователю; возвращает их число (без commit)."""
    now = time.monotonic()
    if not force and now - _last_reminder_run.get(user.id, -1e9) < REMINDER_THROTTLE_SECONDS:
        return 0
    _last_reminder_run[user.id] = now
    today = today or today_local()

    sent = {
        (n.kind, n.entity_id)
        for n in db.query(InAppNotification.kind, InAppNotification.entity_id).filter(
            InAppNotification.user_id == user.id,
            InAppNotification.entity_type == "task_assignment",
            InAppNotification.kind.in_(REMINDER_KINDS),
        )
    }
    created = 0

    def remind(kind: str, assignment: TaskAssignment, message: str) -> None:
        nonlocal created
        key = (kind, str(assignment.id))
        if key in sent:
            return
        sent.add(key)
        in_app_notification_service.notify(db, user, kind, message, entity_type="task_assignment",
                                           entity_id=str(assignment.id))
        created += 1

    group_ids = get_curator_group_ids(db, user, today)
    if group_ids:
        mine = (
            db.query(TaskAssignment).join(Task, Task.id == TaskAssignment.task_id)
            .filter(            TaskAssignment.study_group_id.in_(group_ids), Task.is_closed.is_(False),
                    TaskAssignment.status.in_(EDITABLE_STATUSES), TaskAssignment.locked.is_(False)).all()
        )
        for a in mine:
            days_left = (a.task.due_date - today).days
            title, code, due = a.task.title, a.study_group.code, _fmt(a.task.due_date)
            if days_left < 0:
                remind("task_overdue", a, f"Просрочена задача «{title}» (группа {code}): срок был {due}.")
            elif days_left == 0:
                remind("task_due_today", a, f"Сегодня последний день задачи «{title}» (группа {code}).")
            elif days_left <= REMIND_DAYS_BEFORE:
                remind("task_due_soon", a, f"Скоро срок задачи «{title}» (группа {code}): {due}, осталось {days_left} дн.")

    if is_manager(user):
        threshold = utcnow() - datetime.timedelta(days=REVIEW_WAIT_DAYS)
        waiting = db.query(TaskAssignment).filter(
            TaskAssignment.status == "submitted", TaskAssignment.submitted_at <= threshold
        ).all()
        for a in waiting:
            if can_review(user, a):
                remind("task_review_waiting", a,
                       f"Ждёт проверки больше {REVIEW_WAIT_DAYS} дн.: «{a.task.title}», группа {a.study_group.code}.")
    return created


def assign_new_group(db: Session, group: StudyGroup) -> int:
    """Новая (или вернувшаяся из архива) группа получает назначения по всем открытым задачам,
    в охват которых попадает; задачи зав. отделением/тьютора — только если группа из их отделения.
    Возвращает число созданных назначений (без commit)."""
    if not group.is_active:
        return 0
    today = today_local()
    created = 0
    open_tasks = sorted(
        db.query(Task).filter(Task.is_closed.is_(False), Task.due_date >= today).all(),
        key=lambda t: (t.series_id or t.id, t.step_no),
    )
    existing = {a.task_id for a in db.query(TaskAssignment).filter(TaskAssignment.study_group_id == group.id)}
    for task in open_tasks:
        if task.id in existing or not scope_matches(ScopeDef(**json.loads(task.scope_json)), group):
            continue
        if task.step_no > 1:
            # Шаг цепочки нужен группе только вместе с предыдущим шагом (иначе он вечно закрыт).
            before = db.query(Task.id).filter(Task.series_id == task.series_id, Task.step_no == task.step_no - 1).first()
            if before is None or before[0] not in existing:
                continue
        author = task.author
        if author is not None and RoleCode(author.role.code) in DEPARTMENT_SCOPED_ROLES \
                and author.department_id != group.department_id:
            continue
        locked = task.step_no > 1  # у новой группы предыдущий шаг только что создан — значит, ещё не сдан
        assignment = TaskAssignment(task_id=task.id, study_group_id=group.id, status="new", locked=locked)
        db.add(assignment)
        db.flush()
        existing.add(task.id)
        for curator in ([] if locked else assignees(db, group.id, today)):
            in_app_notification_service.notify(
                db, curator, "task_assigned",
                f"Новая задача «{task.title}» для группы {group.code}, срок — {task.due_date.strftime('%d.%m.%Y')}.",
                entity_type="task_assignment", entity_id=str(assignment.id),
            )
        created += 1
    return created
