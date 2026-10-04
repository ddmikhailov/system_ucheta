"""Задачи от администрации (futures.md, этап 3). Ставят задачи: администратор и
воспитательный отдел — по колледжу, зав. отделением и тьютор — по своему
отделению. Куратор выполняет («Мои задачи»), проверяющий принимает или возвращает."""
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_curator_group_ids, require_roles
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, Task, TaskAssignment, TaskComment, User
from app.schemas.tasks import (
    AnswersIn, AssignmentDetail, AssignmentSummary, CommentIn, CommentRead, FieldDef, MyAssignmentRow,
    ReviewIn, ReviewQueueRow, RowRead, ScopeDef, TaskCreate, TaskDetail, TaskListRow, TaskUpdate,
)
from app.services import attendance_service
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
    )


@router.post("", response_model=TaskDetail, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    task = svc.create_task(db, user, payload)
    log_action(db, user, "task.create", "task", str(task.id), new_value=task.title)
    db.commit()
    return _detail(db, user, task)


@router.get("", response_model=list[TaskListRow])
def list_tasks(user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    today = today_local()
    return [
        TaskListRow(
            id=t.id, title=t.title, collect_mode=t.collect_mode, reviewer_rule=t.reviewer_rule, due_date=t.due_date,
            is_closed=t.is_closed, author_name=t.author.full_name if t.author else None,
            progress=svc.progress(visible, today),
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
        .options(joinedload(TaskAssignment.task), joinedload(TaskAssignment.study_group))
        .filter(TaskAssignment.study_group_id.in_(group_ids)).order_by(Task.due_date, Task.id).all()
    )
    return [
        MyAssignmentRow(
            id=a.id, task_id=a.task_id, title=a.task.title, collect_mode=a.task.collect_mode,
            group_code=a.study_group.code, due_date=a.task.due_date, status=a.status,
            is_overdue=svc.is_overdue(a, today), is_closed=a.task.is_closed,
        )
        for a in rows
    ]


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
    editable = svc.is_assignee(db, user, a) and not task.is_closed and a.status in svc.EDITABLE_STATUSES
    rows_by_student = {r.student_id: r for r in a.rows}
    rows: list[RowRead] = []
    if task.collect_mode != "group":
        for s in attendance_service.get_active_students(db, a.study_group_id, today):
            r = rows_by_student.get(s.id)
            rows.append(RowRead(
                student_id=s.id, student_name=s.full_name,
                is_included=r.is_included if r else task.collect_mode == "student",
                values=json.loads(r.values_json) if r else {},
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
        review_comment=a.review_comment, review_step=a.review_step,
        review_steps=2 if task.reviewer_rule == "two_step" else 1, can_edit=editable, can_submit=editable,
        can_review=svc.can_review(user, a) and a.status == "submitted",
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
    svc.review(db, user, a, payload.action, payload.comment)
    log_action(db, user, f"task.{payload.action}", "task_assignment", str(a.id))
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
        assignments=[_summary(a, today) for a in visible],
    )


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: int, user: User = Depends(require_task_manager), db: Session = Depends(get_db)):
    task = _task_or_404(db, task_id)
    if not svc.visible_assignments(db, user, task) and task.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой задаче")
    return _detail(db, user, task)


@router.patch("/{task_id}", response_model=TaskDetail)
def update_task(
    task_id: int, payload: TaskUpdate, user: User = Depends(require_task_manager), db: Session = Depends(get_db),
):
    task = _task_or_404(db, task_id)
    if not _can_manage(user, task):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Править задачу может её автор или администратор")
    data = payload.model_dump(exclude_unset=True)
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
