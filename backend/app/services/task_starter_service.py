"""Готовые наборы задач для администрации. Сейчас один набор — «Адаптация первого курса» (п. 3.1.5 Положения о кураторе):
шесть задач по неделям для всех групп 1 курса, которые видит ставящий (зав. отделением и тьютор — своё отделение).
Задачи обычные: куратор выполняет их в «Моих задачах», проверяющий принимает или возвращает."""
import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.models import Task, User
from app.schemas.tasks import FieldDef, ScopeDef, TaskCreate
from app.services import task_service

FIRST_YEAR = "first_year"
TITLE_PREFIX = "Адаптация 1 курса"
# Повторный запуск набора в пределах этого срока считается ошибкой (двойной клик, повторная отправка).
RERUN_GUARD_DAYS = 120


def _f(label: str, type_: str, required: bool = True, key: str | None = None) -> dict:
    return {"label": label, "type": type_, "required": required, "key": key}


# (неделя, название, описание, режим сбора, поля)
FIRST_YEAR_STEPS: tuple[tuple[int, str, str, str, list[dict]], ...] = (
    (1, "Знакомство с группой", "Проведите знакомство с группой, расскажите о правилах колледжа и работе с платформой, "
        "соберите контакты родителей.", "group",
     [_f("Знакомство проведено", "bool", key="done"), _f("Дата знакомства", "date", key="date")]),
    (2, "Беседа с каждым студентом", "Проведите ознакомительную беседу с каждым студентом: условия жизни, интересы, "
        "трудности с адаптацией. Подробности записывайте в журнал индивидуальной работы, не здесь.", "student",
     [_f("Дата беседы", "date", key="date"), _f("Нужна дальнейшая работа", "bool", required=False, key="followup")]),
    (3, "Проверка заполнения досье", "Проверьте, что в досье каждого студента заполнены контакты, родители и "
        "основные данные.", "student", [_f("Досье заполнено", "bool", key="done")]),
    (4, "Подключение «Мой ID»", "Убедитесь, что каждый студент подключил «Мой ID» (если модуль включён у колледжа).",
     "student", [_f("«Мой ID» подключён", "bool", key="done")]),
    (5, "Родительское собрание первого курса", "Проведите первое родительское собрание. Протокол соберите в разделе "
        "«Собрания».", "group",
     [_f("Дата собрания", "date", key="date"), _f("Пришло родителей", "number", key="parents")]),
    (6, "Итог адаптации группы", "Подведите итог шести недель: как группа прошла адаптацию, кому нужна поддержка.",
     "group", [_f("Итог адаптации", "text", key="summary"), _f("Студентов с трудностями адаптации", "number", key="hard")]),
)


def descriptor(start: datetime.date | None = None) -> list[dict]:
    start = start or today_local()
    return [
        {"week": week, "title": f"{TITLE_PREFIX}: {title}", "due_date": start + datetime.timedelta(days=7 * week - 1)}
        for week, title, _, _, _ in FIRST_YEAR_STEPS
    ]


def launch_first_year(db: Session, creator: User, start: datetime.date, reviewer_rule: str = "dept_head") -> list[Task]:
    today = today_local()
    if start < today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Дата начала не может быть в прошлом")
    since = today - datetime.timedelta(days=RERUN_GUARD_DAYS)
    recent = db.query(Task).filter(Task.title.like(f"{TITLE_PREFIX}:%"), Task.created_by == creator.id,
                                   Task.created_at >= datetime.datetime.combine(since, datetime.time())).first()
    if recent is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Набор «Адаптация первого курса» вы уже запускали за последние 4 месяца — повторить можно позже")
    scope = ScopeDef(courses=[1])
    task_service.resolve_scope_groups(db, scope, creator)  # понятная ошибка раньше создания первой задачи
    tasks = []
    for week, title, description, mode, fields in FIRST_YEAR_STEPS:
        payload = TaskCreate(
            title=f"{TITLE_PREFIX}: {title}", description=description, collect_mode=mode, reviewer_rule=reviewer_rule,
            due_date=start + datetime.timedelta(days=7 * week - 1),
            fields=[FieldDef(**f) for f in fields], scope=scope,
        )
        tasks.append(task_service.create_task(db, creator, payload))
    return tasks


def tasks_payload(tasks: list[Task]) -> list[dict]:
    return [{"id": t.id, "title": t.title, "due_date": t.due_date} for t in tasks]
