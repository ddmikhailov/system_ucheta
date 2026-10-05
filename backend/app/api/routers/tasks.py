"""Задачи от администрации (futures.md, этап 3). Ставят задачи: администратор и
воспитательный отдел — по колледжу, зав. отделением и тьютор — по своему
отделению. Куратор выполняет («Мои задачи»), проверяющий принимает или возвращает."""
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, Task, TaskAssignment, TaskComment, TaskTemplate, User
from app.schemas.tasks import (
    AnswersIn, AssignmentDetail, AssignmentSummary, CommentIn, CommentRead, FieldDef, MyAssignmentRow,
    HistoryEvent, RemindResult, ReviewIn, ReviewQueueRow, RowRead, ScheduleIn, ScopeDef, ScopePreview, StepRef, TaskCreate, TaskDetail, TaskListRow, TaskSummary, TaskUpdate, TemplateCreate, TemplateRead,
)
from app.services import attendance_service
from app.services.access_service import get_curator_group_ids
from app.services import task_dossier, task_schedule
from app.services import task_service as svc
from app.services.audit_service import log_action

router = APIRouter(prefix="/tasks", tags=["tasks"])

require_task_manager = require_roles(*svc.TASK_MANAGER_ROLES)


def _task_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задача не найдена")
    return task


def _can_manage(user: User, task: Task) -> bool:
    return RoleCode(user.role.code) == RoleCode.ADMIN or task.created_by == user.id


def _summary(a: TaskAssignment, today) -> AssignmentSummary:
    g = a.study_group
    return AssignmentSummary(
        id=a.id, study_group_id=g.id, group_code=g.code, course=g.course, department_name=g.department.name,
        status=a.status, is_overdue=svc.is_overdue(a, today), submitted_at=a.submitted_at, reviewed_at=a.reviewed_at,
        reviewed_by_name=a.reviewer.full_name if a.reviewer else None, is_locked=a.locked,
    )


@router.post("", response_model=TaskDetail, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    task = svc.create_task(db, user, payload)
    log_action(db, user, "task.create", "task", str(task.id), new_value=task.title)
    db.commit()
    return _detail(db, user, task)


@router.post("/scope-preview", response_model=ScopePreview)
def scope_preview(scope: ScopeDef, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    """Сколько групп, студентов и кураторов получат задачу — мастер показывает это до создания."""
    return svc.scope_preview(db, user, scope)


@router.get("/dossier-fields")
def dossier_fields(user: User = Depends(require_task_manager)):
    """Поля досье, к которым можно привязать поле формы (для конструктора)."""
    return task_dossier.targets_list()


def _step_totals(db: Session) -> dict[int, int]:
    """{series_id: число шагов} только для настоящих цепочек (больше одного шага)."""
    rows = db.query(Task.series_id, func.count(Task.id)).filter(Task.series_id.isnot(None)).group_by(Task.series_id).all()
    return {sid: n for sid, n in rows if n > 1}


def _template_read(t: TaskTemplate, user: User) -> TemplateRead:
    data = json.loads(t.payload_json)
    return TemplateRead(
        id=t.id, name=t.name, author_name=t.author.full_name if t.author else None, created_at=t.created_at,
        can_manage=RoleCode(user.role.code) == RoleCode.ADMIN or t.created_by == user.id,
        title=data["title"], description=data.get("description"), collect_mode=data["collect_mode"],
        reviewer_rule=data["reviewer_rule"], fields=[FieldDef(**f) for f in data["fields"]],
        scope=ScopeDef(**data["scope"]), repeat=t.repeat, repeat_day=t.repeat_day, due_offset_days=t.due_offset_days,
        next_run=t.next_run, last_run_date=t.last_run_date, last_error=t.last_error,
    )


@router.get("/templates", response_model=list[TemplateRead])
def list_templates(user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    return [_template_read(t, user) for t in db.query(TaskTemplate).order_by(TaskTemplate.name, TaskTemplate.id)]


@router.post("/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateCreate, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    """Сохраняет существующую задачу как шаблон (без срока)."""
    task = _task_or_404(db, payload.task_id)
    if not svc.visible_assignments(db, user, task) and task.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой задаче")
    template = svc.template_from_task(task, user, payload.name)
    db.add(template)
    db.flush()
    log_action(db, user, "task.template_create", "task_template", str(template.id), new_value=template.name)
    db.commit()
    db.refresh(template)
    return _template_read(template, user)


@router.put("/templates/{template_id}/schedule", response_model=TemplateRead)
def set_template_schedule(
    template_id: int, payload: ScheduleIn, user: User = Depends(require_task_manager), db: Session = Depends(get_db),
):
    """Расписание периодического запуска. Меняет автор шаблона или администратор; запуск идёт от имени автора."""
    template = db.get(TaskTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Шаблон не найден")
    if not _template_read(template, user).can_manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Расписание меняет автор шаблона или администратор")
    task_schedule.set_schedule(template, payload.repeat, payload.repeat_day, payload.due_offset_days)
    log_action(db, user, "task.template_schedule", "task_template", str(template.id),
               new_value=f"{payload.repeat or 'off'}:{payload.repeat_day}:{payload.due_offset_days}")
    db.commit()
    db.refresh(template)
    return _template_read(template, user)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    template = db.get(TaskTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Шаблон не найден")
    if not _template_read(template, user).can_manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Удалить шаблон может его автор или администратор")
    log_action(db, user, "task.template_delete", "task_template", str(template.id), old_value=template.name)
    # Созданные по шаблону задачи остаются, просто теряют связь с ним.
    db.query(Task).filter(Task.template_id == template.id).update({"template_id": None, "period_key": None})
    db.delete(template)
    db.commit()


@router.get("", response_model=list[TaskListRow])
def list_tasks(user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    today = today_local()
    totals = _step_totals(db)
    return [
        TaskListRow(
            id=t.id, title=t.title, collect_mode=t.collect_mode, reviewer_rule=t.reviewer_rule, due_date=t.due_date,
            is_closed=t.is_closed, author_id=t.created_by, author_name=t.author.full_name if t.author else None,
            progress=svc.progress(visible, today), step_no=t.step_no, step_total=totals.get(t.series_id),
        )
        for t, visible in svc.manager_tasks(db, user)
    ]


@router.get("/my", response_model=list[MyAssignmentRow])
def my_assignments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_local()
    group_ids = get_curator_group_ids(db, user, today)
    if not group_ids:
        return []
    rows = (
        db.query(TaskAssignment).join(Task, Task.id == TaskAssignment.task_id)
        .options(
            joinedload(TaskAssignment.task), joinedload(TaskAssignment.study_group), selectinload(TaskAssignment.rows),
        )
        .filter(TaskAssignment.study_group_id.in_(group_ids)).order_by(Task.due_date, Task.id).all()
    )
    totals = _step_totals(db)
    rosters: dict[int, set[int]] = {}
    result = []
    for a in rows:
        filled, total = svc.fill_progress(db, a, today, rosters)
        result.append(MyAssignmentRow(
            id=a.id, task_id=a.task_id, title=a.task.title, collect_mode=a.task.collect_mode,
            group_code=a.study_group.code, due_date=a.task.due_date, status=a.status,
            is_overdue=svc.is_overdue(a, today), is_closed=a.task.is_closed, is_locked=a.locked,
            step_no=a.task.step_no, step_total=totals.get(a.task.series_id), filled=filled, total=total,
            review_comment=a.review_comment if a.status == "returned" else None,
        ))
    return result


@router.get("/review-queue", response_model=list[ReviewQueueRow])
def review_queue(user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    today = today_local()
    rows = (
        db.query(TaskAssignment).filter(TaskAssignment.status == "submitted")
        .options(joinedload(TaskAssignment.task), joinedload(TaskAssignment.study_group).joinedload(StudyGroup.department))
        .order_by(TaskAssignment.submitted_at).all()
    )
    return [
        ReviewQueueRow(
            id=a.id, task_id=a.task_id, title=a.task.title, group_code=a.study_group.code,
            department_name=a.study_group.department.name, due_date=a.task.due_date,
            submitted_at=a.submitted_at, is_overdue=svc.is_overdue(a, today),
        )
        for a in rows if svc.can_review(user, a)
    ]


def _detail_assignment(db: Session, user: User, a: TaskAssignment) -> AssignmentDetail:
    task = a.task
    today = today_local()
    editable = svc.is_assignee(db, user, a) and not task.is_closed and not a.locked and a.status in svc.EDITABLE_STATUSES
    rows_by_student = {r.student_id: r for r in a.rows}
    rows: list[RowRead] = []
    if task.collect_mode != "group":
        students = attendance_service.get_active_students(db, a.study_group_id, today)
        # Куратору форма открывается заполненной из досье (только строки, которые он ещё не сохранял);
        # другим просматривающим данные досье по задаче не раскрываем.
        prefilled = task_dossier.prefill(db, svc.task_fields(task), [s.id for s in students]) if editable else {}
        for s in students:
            r = rows_by_student.get(s.id)
            rows.append(RowRead(
                student_id=s.id, student_name=s.full_name,
                is_included=r.is_included if r else task.collect_mode == "student",
                values=json.loads(r.values_json) if r else prefilled.get(s.id, {}),
                from_dossier=r is None and bool(prefilled.get(s.id)),
            ))
    comments = sorted(a.comments, key=lambda c: (c.created_at, c.id))
    return AssignmentDetail(
        id=a.id, task_id=task.id, title=task.title, description=task.description, collect_mode=task.collect_mode,
        reviewer_rule=task.reviewer_rule, due_date=task.due_date, is_closed=task.is_closed,
        fields=[FieldDef(**f) for f in svc.task_fields(task)], study_group_id=a.study_group_id,
        group_code=a.study_group.code, status=a.status, is_overdue=svc.is_overdue(a, today),
        group_values=json.loads(a.group_values_json or "{}"), rows=rows,
        comments=[CommentRead(id=c.id, student_id=c.student_id, author_name=c.author.full_name if c.author else None,
                              text=c.text, created_at=c.created_at) for c in comments],
        review_comment=a.review_comment, submitted_at=a.submitted_at, reviewed_at=a.reviewed_at,
        reviewed_by_name=a.reviewer.full_name if a.reviewer else None,
        history=[HistoryEvent(**e) for e in svc.assignment_history(db, a)], review_step=a.review_step,
        review_steps=2 if task.reviewer_rule == "two_step" else 1, can_edit=editable, can_submit=editable,
        can_review=svc.can_review(user, a) and a.status == "submitted",
        is_locked=a.locked, locked_reason=svc.lock_reason(db, a), step_no=task.step_no,
        step_total=_step_totals(db).get(task.series_id),
    )


@router.get("/assignments/{assignment_id}", response_model=AssignmentDetail)
def get_assignment(assignment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _detail_assignment(db, user, svc.get_assignment_for(db, user, assignment_id))


@router.put("/assignments/{assignment_id}/answers", response_model=AssignmentDetail)
def save_answers(
    assignment_id: int, payload: AnswersIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    a = svc.get_assignment_for(db, user, assignment_id)
    svc.save_answers(db, user, a, payload.group_values, payload.rows)
    db.commit()
    return _detail_assignment(db, user, a)


@router.post("/assignments/{assignment_id}/submit", response_model=AssignmentDetail)
def submit_assignment(assignment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = svc.get_assignment_for(db, user, assignment_id)
    svc.submit(db, user, a)
    log_action(db, user, "task.submit", "task_assignment", str(a.id))
    db.commit()
    return _detail_assignment(db, user, a)


@router.post("/assignments/{assignment_id}/review", response_model=AssignmentDetail)
def review_assignment(
    assignment_id: int, payload: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    a = svc.get_assignment_for(db, user, assignment_id)
    step = a.review_step  # ступень, на которой принято решение (после принятия на первой она уже вторая)
    svc.review(db, user, a, payload.action, payload.comment)
    log_action(db, user, f"task.{payload.action}", "task_assignment", str(a.id), new_value=f"step:{step}")
    db.commit()
    return _detail_assignment(db, user, a)


@router.post("/assignments/{assignment_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
def add_comment(
    assignment_id: int, payload: CommentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    a = svc.get_assignment_for(db, user, assignment_id)
    comment: TaskComment = svc.add_comment(db, user, a, payload.student_id, payload.text)
    db.commit()
    db.refresh(comment)
    return CommentRead(id=comment.id, student_id=comment.student_id, author_name=user.full_name,
                       text=comment.text, created_at=comment.created_at)


def _detail(db: Session, user: User, task: Task) -> TaskDetail:
    today = today_local()
    visible = svc.visible_assignments(db, user, task)
    return TaskDetail(
        id=task.id, title=task.title, description=task.description, collect_mode=task.collect_mode,
        reviewer_rule=task.reviewer_rule, due_date=task.due_date, is_closed=task.is_closed,
        author_id=task.created_by, author_name=task.author.full_name if task.author else None,
        fields=[FieldDef(**f) for f in svc.task_fields(task)], scope=ScopeDef(**json.loads(task.scope_json)),
        can_manage=_can_manage(user, task), progress=svc.progress(visible, today),
        assignments=[_summary(a, today) for a in visible], step_no=task.step_no, unlock_on=task.unlock_on,
        steps=[StepRef(id=s.id, title=s.title, step_no=s.step_no, due_date=s.due_date) for s in svc.series_steps(db, task)],
    )


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    task = _task_or_404(db, task_id)
    if not svc.visible_assignments(db, user, task) and task.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой задаче")
    return _detail(db, user, task)


def _visible_task_or_403(db: Session, user: User, task_id: int) -> Task:
    task = _task_or_404(db, task_id)
    if not svc.visible_assignments(db, user, task) and task.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой задаче")
    return task


@router.post("/{task_id}/remind", response_model=RemindResult)
def remind_lagging(task_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    """Напомнить кураторам групп, которые ещё не отправили ответ, — в пределах видимых пользователю групп."""
    task = _visible_task_or_403(db, user, task_id)
    if task.is_closed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Задача закрыта — напоминать не о чем")
    sent, skipped = svc.remind_lagging(db, user, task)
    if sent:
        log_action(db, user, "task.remind", "task", str(task.id), new_value=f"groups:{sent}")
    db.commit()
    return RemindResult(sent=sent, skipped=skipped)


@router.get("/{task_id}/summary", response_model=TaskSummary)
def task_summary(task_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    return svc.answers_summary(db, user, _visible_task_or_403(db, user, task_id))


@router.patch("/{task_id}", response_model=TaskDetail)
def update_task(
    task_id: int, payload: TaskUpdate, user: User = Depends(require_task_manager), db: Session = Depends(get_db),
):
    task = _task_or_404(db, task_id)
    if not _can_manage(user, task):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Править задачу может её автор или администратор")
    data = payload.model_dump(exclude_unset=True)
    if data.get("due_date") is not None and data["due_date"] != task.due_date:
        svc.reset_deadline_reminders(db, task)  # новый срок — напоминания о сроках начинаются заново
    for key in ("title", "description", "due_date", "is_closed"):
        if key in data and data[key] is not None:
            setattr(task, key, data[key].strip() if isinstance(data[key], str) else data[key])
    log_action(db, user, "task.update", "task", str(task.id))
    db.commit()
    return _detail(db, user, task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    task = _task_or_404(db, task_id)
    if not _can_manage(user, task):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Удалить задачу может её автор или администратор")
    if svc.next_step(db, task) is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "У задачи есть следующий шаг — удаляйте шаги с последнего")
    if any(a.status != "new" for a in task.assignments):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "По задаче уже есть ответы — закройте её вместо удаления")
    log_action(db, user, "task.delete", "task", str(task.id), old_value=task.title)
    db.delete(task)
    db.commit()


@router.get("/{task_id}/export")
def export_task(task_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    task = _task_or_404(db, task_id)
    if not svc.visible_assignments(db, user, task):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой задаче")
    return Response(
        content=svc.export_workbook(db, user, task),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="task_{task.id}.xlsx"'},
    )
