"""Периодические задачи (этап 4в): расписание лежит на шаблоне, очередная задача
создаётся при открытии платформы (отдельного планировщика нет — как и у напоминаний о сроках).

  * «Каждый месяц» — в выбранный день месяца; «Каждый семестр» — в тот же день сентября и февраля.
  * Срок новой задачи = день запуска + N дней. К названию добавляется период («— Октябрь 2026»),
    чтобы задачи одного шаблона различались.
  * Платформу долго не открывали — создаётся ОДНА актуальная задача, а не пачка пропущенных.
  * Двойной запуск исключён: очередь занимается условным UPDATE (next_run), а на (шаблон, период) стоит
    уникальность — два одновременных опроса не создадут две задачи.
  * Задача создаётся от имени автора шаблона и с его правами на охват (зав. отделением — только своё
    отделение). Если автор уже не может создавать задачи, запуск пропускается, причина видна в шаблоне."""
import datetime
import json
import time

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.models import Task, TaskTemplate
from app.schemas.tasks import TaskCreate
from app.services import task_service
from app.services.audit_service import log_action

REPEAT_KINDS = ("monthly", "semester")
SEMESTER_MONTHS = (2, 9)  # февраль и сентябрь
MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
RUN_THROTTLE_SECONDS = 300
_last_run = 0.0


def reset_throttle() -> None:
    global _last_run
    _last_run = 0.0


def next_occurrence(kind: str, day: int, from_date: datetime.date) -> datetime.date:
    """Ближайшая дата запуска не раньше from_date."""
    months = SEMESTER_MONTHS if kind == "semester" else tuple(range(1, 13))
    year, month = from_date.year, from_date.month
    for _ in range(25):
        if month in months:
            candidate = datetime.date(year, month, day)
            if candidate >= from_date:
                return candidate
        month += 1
        if month > 12:
            month, year = 1, year + 1
    raise ValueError("не удалось подобрать дату запуска")  # недостижимо при day ≤ 28


def period_label(kind: str, run_date: datetime.date) -> str:
    if kind == "semester":
        return f"{'осенний' if run_date.month >= 8 else 'весенний'} семестр {run_date.year}"
    return f"{MONTHS_RU[run_date.month - 1].capitalize()} {run_date.year}"


def set_schedule(template: TaskTemplate, repeat: str, day: int, due_offset_days: int,
                 today: datetime.date | None = None) -> None:
    today = today or today_local()
    template.repeat = repeat
    template.repeat_day = day
    template.due_offset_days = due_offset_days
    template.last_error = None
    template.next_run = next_occurrence(repeat, day, today) if repeat in REPEAT_KINDS else None


def run_due_templates(db: Session, today: datetime.date | None = None, force: bool = False) -> int:
    """Создаёт задачи по шаблонам, у которых подошёл срок запуска. Возвращает число созданных."""
    global _last_run
    now = time.monotonic()
    if not force and _last_run and now - _last_run < RUN_THROTTLE_SECONDS:
        return 0
    _last_run = now
    today = today or today_local()
    due = db.query(TaskTemplate).filter(TaskTemplate.repeat.in_(REPEAT_KINDS), TaskTemplate.next_run <= today).all()
    created = 0
    for template in due:
        created += _run_one(db, template, today)
    return created


def _run_one(db: Session, template: TaskTemplate, today: datetime.date) -> int:
    old_next = template.next_run
    new_next = next_occurrence(template.repeat, template.repeat_day, today + datetime.timedelta(days=1))
    # Занимаем запуск: если другой запрос успел раньше, rowcount будет 0.
    claimed = db.execute(
        update(TaskTemplate).where(TaskTemplate.id == template.id, TaskTemplate.next_run == old_next)
        .values(next_run=new_next)
    ).rowcount
    if not claimed:
        db.rollback()
        return 0
    db.refresh(template)
    author = template.author
    period_key = today.strftime("%Y-%m")
    try:
        if author is None or not author.is_active or not task_service.is_manager(author):
            raise HTTPException(400, "автор шаблона больше не может создавать задачи")
        if db.query(Task.id).filter(Task.template_id == template.id, Task.period_key == period_key).first():
            raise HTTPException(400, "за этот период задача уже создана")
        data = json.loads(template.payload_json)
        payload = TaskCreate(
            title=f"{data['title']} — {period_label(template.repeat, today)}"[:255],
            description=data.get("description"), collect_mode=data["collect_mode"], reviewer_rule=data["reviewer_rule"],
            due_date=today + datetime.timedelta(days=template.due_offset_days),
            fields=data["fields"], scope=data["scope"],
        )
        task = task_service.create_task(db, author, payload)
        task.template_id = template.id
        task.period_key = period_key
        template.last_run_date = today
        template.last_error = None
        log_action(db, author, "task.scheduled_create", "task", str(task.id), new_value=f"template:{template.id}")
        db.commit()
        return 1
    except HTTPException as exc:
        db.rollback()
        # rollback откатил и «занятие» запуска — повторяем его и фиксируем причину пропуска
        db.execute(update(TaskTemplate).where(TaskTemplate.id == template.id).values(
            next_run=new_next, last_error=str(exc.detail)[:500]))
        log_action(db, None, "task.scheduled_skip", "task_template", str(template.id), new_value=str(exc.detail)[:200])
        db.commit()
        return 0
