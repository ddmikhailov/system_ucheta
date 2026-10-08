"""Питание: кто питается, недельная подача куратора, правки по дням и прогноз для неподавших.

Правила (решения заказчика, 08.10.2026):
  * По умолчанию питаются все присутствующие в колледже. Студент «на договорной основе» (поле финансирования
    в досье либо признак группы) не питается, и включить ему питание нельзя.
  * Куратор подаёт питание на следующую неделю: задача появляется в понедельник 09:00, срок — четверг 16:00.
    После срока подать можно, но в свод до подачи идёт прогноз.
  * Отдельный день куратор может поправить до 10:00 предыдущего учебного дня.
  * Прогноз для неподавшей группы = питающиеся × (средняя посещаемость за последнюю неделю + 10 п.п.),
    потолок — число питающихся, округление до целых. Подсказка куратору — то же без +10 п.п.
  * Отдельного планировщика нет: задача создаётся, а число считается при открытии платформы или свода."""
import datetime
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.roles import DEPARTMENT_SCOPED_ROLES
from app.core.time import now_local, today_local, utcnow
from app.models import (
    AttendanceMark, CuratorAssignment, DaySubmission, MarkCode, MealDayOverride, MealSubmission, RoleCode, Student, StudentMeal,
    StudentProfile, StudyGroup, Task, TaskAssignment, User,
)
from app.schemas.tasks import ScopeDef
from app.services import calendar_service, in_app_notification_service, task_service
from app.services.audit_service import log_action

TASK_KIND = "meal"
TASK_APPEARS = (0, datetime.time(9, 0))  # понедельник 09:00 — за неделю до недели, на которую подают
SUBMIT_DEADLINE_WEEKDAY, SUBMIT_DEADLINE_TIME = 3, datetime.time(16, 0)  # четверг 16:00 той же недели
DAY_CUTOFF_TIME = datetime.time(10, 0)  # правка дня — до 10:00 предыдущего учебного дня
FORECAST_MARGIN_PP = 10
ATTENDANCE_WINDOW_DAYS = 7


def _bad(message: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, message)


# ---------- даты и сроки ----------

def week_start(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def next_week_start(today: datetime.date) -> datetime.date:
    return week_start(today) + datetime.timedelta(days=7)


def submit_deadline(target_week: datetime.date) -> datetime.datetime:
    """Срок подачи на неделю, начинающуюся в понедельник `target_week`: четверг 16:00 предыдущей недели."""
    prev_monday = target_week - datetime.timedelta(days=7)
    return datetime.datetime.combine(prev_monday + datetime.timedelta(days=SUBMIT_DEADLINE_WEEKDAY), SUBMIT_DEADLINE_TIME)


def task_appears_at(target_week: datetime.date) -> datetime.datetime:
    prev_monday = target_week - datetime.timedelta(days=7)
    return datetime.datetime.combine(prev_monday + datetime.timedelta(days=TASK_APPEARS[0]), TASK_APPEARS[1])


CUTOFF_MAX_LOOKBACK_DAYS = 4  # после каникул срок «предыдущего учебного дня» не уходит дальше этого


def cutoff_for(study_days: list[datetime.date], day: datetime.date) -> datetime.datetime:
    """Последний момент, когда можно править число на `day`: 10:00 предыдущего учебного дня (по списку учебных дней
    группы, отсортированному по возрастанию). Если учебного дня рядом нет (каникулы) — 10:00 за четыре дня до `day`,
    иначе первый день после каникул был бы закрыт задолго до своего наступления."""
    earliest = day - datetime.timedelta(days=CUTOFF_MAX_LOOKBACK_DAYS)
    prev = next((d for d in reversed(study_days) if d < day), None)
    if prev is None or prev < earliest:
        prev = earliest
    return datetime.datetime.combine(prev, DAY_CUTOFF_TIME)


def round_half_up(value: float) -> int:
    return int(value + 0.5)


def forecast_count(eaters: int, percent: float | None) -> int:
    if percent is None or eaters == 0:
        return eaters
    return min(eaters, round_half_up(eaters * min(percent + FORECAST_MARGIN_PP, 100) / 100))


def hint_count(eaters: int, percent: float | None) -> int:
    if percent is None or eaters == 0:
        return eaters
    return min(eaters, round_half_up(eaters * percent / 100))


# ---------- кто питается ----------

@dataclass
class StudentMealState:
    student: Student
    eats: bool
    locked_reason: str | None  # почему включить питание нельзя


def current_students(db: Session, group_ids: list[int], on_date: datetime.date) -> dict[int, list[Student]]:
    if not group_ids:
        return {}
    rows = db.execute(
        select(Student).where(
            Student.study_group_id.in_(group_ids), Student.enrolled_at <= on_date,
            (Student.left_at.is_(None)) | (Student.left_at >= on_date),
        ).order_by(Student.last_name, Student.first_name)
    ).scalars().all()
    result: dict[int, list[Student]] = defaultdict(list)
    for s in rows:
        result[s.study_group_id].append(s)
    return result


def student_states(
    db: Session, groups: list[StudyGroup], on_date: datetime.date,
) -> dict[int, list[StudentMealState]]:
    by_group = current_students(db, [g.id for g in groups], on_date)
    ids = [s.id for students in by_group.values() for s in students]
    funding: dict[int, str | None] = {}
    choices: dict[int, bool] = {}
    if ids:
        funding = dict(db.execute(select(StudentProfile.student_id, StudentProfile.funding).where(StudentProfile.student_id.in_(ids))).all())
        choices = dict(db.execute(select(StudentMeal.student_id, StudentMeal.eats).where(StudentMeal.student_id.in_(ids))).all())
    result: dict[int, list[StudentMealState]] = {}
    for group in groups:
        group_contract = group.funding == "contract"
        states = []
        for s in by_group.get(group.id, []):
            if group_contract:
                states.append(StudentMealState(s, False, "Группа на договорной основе"))
            elif funding.get(s.id) == "contract":
                states.append(StudentMealState(s, False, "Обучение на договорной основе"))
            else:
                states.append(StudentMealState(s, choices.get(s.id, True), None))
        result[group.id] = states
    return result


def eaters_count(states: list[StudentMealState]) -> int:
    return sum(1 for s in states if s.eats)


# ---------- посещаемость за последнюю неделю ----------

def attendance_percent(db: Session, group_ids: list[int], end: datetime.date) -> dict[int, float | None]:
    """Средняя посещаемость группы за 7 дней по `end` включительно — по сданным дням. Пропуск — любая отметка,
    не считающаяся присутствием (как в витринах). Нет сданных дней — None."""
    if not group_ids:
        return {}
    start = end - datetime.timedelta(days=ATTENDANCE_WINDOW_DAYS - 1)
    submitted: dict[int, set[datetime.date]] = defaultdict(set)
    for gid, day in db.execute(
        select(DaySubmission.study_group_id, DaySubmission.date)
        .where(DaySubmission.study_group_id.in_(group_ids), DaySubmission.date >= start, DaySubmission.date <= end)
    ).all():
        submitted[gid].add(day)
    absent: dict[tuple[int, datetime.date], int] = {}
    for gid, day, n in db.execute(
        select(Student.study_group_id, AttendanceMark.date, func.count(AttendanceMark.id))
        .join(Student, Student.id == AttendanceMark.student_id)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(Student.study_group_id.in_(group_ids), AttendanceMark.date >= start, AttendanceMark.date <= end,
               MarkCode.counts_as_present.is_(False))
        .group_by(Student.study_group_id, AttendanceMark.date)
    ).all():
        absent[(gid, day)] = n
    students: dict[int, list[Student]] = defaultdict(list)
    for s in db.execute(select(Student).where(Student.study_group_id.in_(group_ids), Student.enrolled_at <= end)).scalars():
        students[s.study_group_id].append(s)
    result: dict[int, float | None] = {}
    for gid in group_ids:
        total_in_list = total_absent = 0
        for day in submitted.get(gid, ()):
            in_list = sum(1 for s in students.get(gid, []) if s.enrolled_at <= day and (s.left_at is None or s.left_at >= day))
            total_in_list += in_list
            total_absent += min(absent.get((gid, day), 0), in_list)
        result[gid] = round((total_in_list - total_absent) / total_in_list * 100, 1) if total_in_list else None
    return result


# ---------- неделя группы ----------

@dataclass
class DayValue:
    date: datetime.date
    count: int
    source: str  # submitted / edited / forecast
    open: bool  # правку ещё можно внести
    cutoff: datetime.datetime


@dataclass
class GroupWeek:
    group: StudyGroup
    week_start: datetime.date
    eaters: int
    percent: float | None
    hint: int
    forecast: int
    submission: MealSubmission | None
    status: str  # submitted / pending / forecast
    deadline: datetime.datetime
    days: list[DayValue] = field(default_factory=list)


def build_weeks(
    db: Session, groups: list[StudyGroup], target_week: datetime.date, now: datetime.datetime | None = None,
) -> dict[int, GroupWeek]:
    now = now or now_local()
    today = now.date()
    ids = [g.id for g in groups]
    if not ids:
        return {}
    basis_date = max(today, target_week)
    states = student_states(db, groups, basis_date)
    percents = attendance_percent(db, ids, min(today, target_week - datetime.timedelta(days=1)))
    submissions = {
        s.study_group_id: s for s in db.execute(
            select(MealSubmission).where(MealSubmission.study_group_id.in_(ids), MealSubmission.week_start == target_week)
        ).scalars()
    }
    week_end = target_week + datetime.timedelta(days=6)
    overrides = {
        (o.study_group_id, o.date): o for o in db.execute(
            select(MealDayOverride).where(
                MealDayOverride.study_group_id.in_(ids), MealDayOverride.date >= target_week, MealDayOverride.date <= week_end)
        ).scalars()
    }
    deadline = submit_deadline(target_week)
    # Календарь всех групп — двумя запросами (а не по запросу на группу и день): неделя плюс две недели назад,
    # чтобы найти «предыдущий учебный день» для понедельника.
    calendar = calendar_service.study_days_by_group(db, target_week - datetime.timedelta(days=14), week_end, groups)
    result: dict[int, GroupWeek] = {}
    for group in groups:
        eaters = eaters_count(states.get(group.id, []))
        percent = percents.get(group.id)
        submission = submissions.get(group.id)
        forecast = forecast_count(eaters, percent)
        week = GroupWeek(
            group=group, week_start=target_week, eaters=eaters, percent=percent, hint=hint_count(eaters, percent),
            forecast=forecast, submission=submission, deadline=deadline,
            status="submitted" if submission else ("pending" if now < deadline else "forecast"),
        )
        group_days = calendar[group.id]
        for day in (d for d in group_days if d >= target_week):
            cutoff = cutoff_for(group_days, day)
            override = overrides.get((group.id, day))
            if override is not None:
                count, source = override.count, "edited"
            elif submission is not None:
                count, source = submission.count, "submitted"
            else:
                count, source = forecast, "forecast"
            week.days.append(DayValue(day, min(count, eaters) if source != "edited" else count, source, now < cutoff, cutoff))
        result[group.id] = week
    return result


# ---------- действия куратора ----------

def set_student_eats(db: Session, user: User, group: StudyGroup, student_id: int, eats: bool) -> None:
    states = student_states(db, [group], today_local())[group.id]
    state = next((s for s in states if s.student.id == student_id), None)
    if state is None:
        raise _bad("Студент не из этой группы", status.HTTP_404_NOT_FOUND)
    if state.locked_reason and eats:
        raise _bad(f"{state.locked_reason}: питание включить нельзя", status.HTTP_409_CONFLICT)
    row = db.get(StudentMeal, student_id)
    if row is None:
        row = StudentMeal(student_id=student_id, eats=eats)
        db.add(row)
    row.eats, row.updated_by_user_id, row.updated_at = eats, user.id, utcnow()
    log_action(db, user, "meal.student", "student", str(student_id), new_value="eats" if eats else "no")


def _check_count(count: int, eaters: int) -> None:
    if count < 0:
        raise _bad("Число не может быть отрицательным")
    if count > eaters:
        raise _bad(f"Нельзя заказать больше, чем питающихся в группе ({eaters})")


def submit_week(
    db: Session, user: User, group: StudyGroup, target_week: datetime.date, count: int, now: datetime.datetime | None = None,
) -> GroupWeek:
    now = now or now_local()
    if target_week.weekday() != 0:
        raise _bad("Неделя начинается с понедельника")
    this_week = week_start(now.date())
    if target_week not in (this_week, this_week + datetime.timedelta(days=7)):
        raise _bad("Подать питание можно на текущую или на следующую неделю")
    week = build_weeks(db, [group], target_week, now)[group.id]
    open_days = [d for d in week.days if d.open]
    if not open_days:
        raise _bad("Приём питания на эту неделю закрыт: правки по всем дням уже недоступны", status.HTTP_409_CONFLICT)
    _check_count(count, week.eaters)
    # Закрытые дни не меняются задним числом: фиксируем для них то, что действовало до этой подачи.
    for day in week.days:
        if not day.open and day.source != "edited":
            db.add(MealDayOverride(study_group_id=group.id, date=day.date, count=day.count, edited_by_user_id=user.id))
    submission = week.submission
    if submission is None:
        submission = MealSubmission(study_group_id=group.id, week_start=target_week, count=count)
        db.add(submission)
    submission.count, submission.submitted_by_user_id, submission.submitted_at = count, user.id, utcnow()
    log_action(db, user, "meal.submit_week", "study_group", str(group.id), new_value=f"{target_week}:{count}")
    _complete_task(db, group, target_week)
    db.flush()
    return build_weeks(db, [group], target_week, now)[group.id]


def set_day_count(
    db: Session, user: User, group: StudyGroup, day: datetime.date, count: int | None, now: datetime.datetime | None = None,
) -> GroupWeek:
    """Правка числа на день (count=None — вернуть недельное). Только до 10:00 предыдущего учебного дня."""
    now = now or now_local()
    target_week = week_start(day)
    week = build_weeks(db, [group], target_week, now)[group.id]
    value = next((d for d in week.days if d.date == day), None)
    if value is None:
        raise _bad(f"{day.strftime('%d.%m.%Y')} — не учебный день группы")
    if not value.open:
        raise _bad(
            f"Правки на {day.strftime('%d.%m.%Y')} закрыты: их принимают до {value.cutoff.strftime('%d.%m.%Y %H:%M')}",
            status.HTTP_409_CONFLICT,
        )
    row = db.execute(select(MealDayOverride).where(MealDayOverride.study_group_id == group.id, MealDayOverride.date == day)).scalar_one_or_none()
    if count is None:
        if row is not None:
            db.delete(row)
    else:
        _check_count(count, week.eaters)
        if row is None:
            row = MealDayOverride(study_group_id=group.id, date=day, count=count)
            db.add(row)
        row.count, row.edited_by_user_id, row.edited_at = count, user.id, utcnow()
    log_action(db, user, "meal.set_day", "study_group", str(group.id), new_value=f"{day}:{count}")
    db.flush()
    return build_weeks(db, [group], target_week, now)[group.id]


# ---------- задача «Подать питание» ----------

def _task_period(target_week: datetime.date) -> str:
    return f"meal-{target_week.isoformat()}"


def _complete_task(db: Session, group: StudyGroup, target_week: datetime.date) -> None:
    task = db.execute(select(Task).where(Task.kind == TASK_KIND, Task.period_key == _task_period(target_week))).scalar_one_or_none()
    if task is None:
        return
    assignment = db.execute(select(TaskAssignment).where(TaskAssignment.task_id == task.id, TaskAssignment.study_group_id == group.id)).scalar_one_or_none()
    if assignment is not None and assignment.status != "accepted":
        assignment.status = "accepted"
        assignment.submitted_at = utcnow()
        assignment.reviewed_at = utcnow()
        assignment.reviewed_by = None
        assignment.review_step = 1


# Задачу создаёт тот запрос, который первым открыл платформу после понедельника 09:00. Колокольчик опрашивает
# сервер из многих вкладок сразу, а потоки запросов идут параллельно, поэтому без замка две вкладки создали бы по
# задаче (уникальности на (вид, период) в БД нет). Процесс один (см. CLAUDE.md), так что замка и памяти достаточно.
_task_lock = threading.Lock()
_ensured_week: datetime.date | None = None


def reset_weekly_task_cache() -> None:
    global _ensured_week
    _ensured_week = None


def ensure_weekly_task(db: Session, now: datetime.datetime | None = None) -> Task | None:
    """Создаёт задачу «Подать питание на следующую неделю», когда пришло её время (понедельник 09:00 и позже).
    Вызывается при открытии платформы; повторный вызов ничего не делает и в БД не ходит."""
    global _ensured_week
    now = now or now_local()
    target_week = next_week_start(now.date())
    if now < task_appears_at(target_week) or _ensured_week == target_week:
        return None
    with _task_lock:
        if _ensured_week == target_week:
            return None
        task = _create_weekly_task(db, now, target_week)
        _ensured_week = target_week
        return task


def _create_weekly_task(db: Session, now: datetime.datetime, target_week: datetime.date) -> Task | None:
    period = _task_period(target_week)
    if db.execute(select(Task.id).where(Task.kind == TASK_KIND, Task.period_key == period)).first():
        return None
    groups = [g for g in db.query(StudyGroup).filter(StudyGroup.is_active.is_(True)).all() if g.funding != "contract"]
    states = student_states(db, groups, max(now.date(), target_week))
    groups = [g for g in groups if eaters_count(states.get(g.id, [])) > 0]
    if not groups:
        return None
    last = target_week + datetime.timedelta(days=5)
    deadline = submit_deadline(target_week)
    task = Task(
        title=f"Подать питание на следующую неделю ({target_week.strftime('%d.%m')}–{last.strftime('%d.%m')})",
        description=(
            f"Отметьте во вкладке «Питание» вашей группы, кто питается, и подайте число на неделю. "
            f"Срок — {deadline.strftime('%d.%m')} {deadline.strftime('%H:%M')}. Если не подать, в свод пойдёт прогноз по посещаемости."
        ),
        created_by=None, collect_mode="group", reviewer_rule="none", due_date=deadline.date(), fields_json="[]",
        scope_json=ScopeDef(all_groups=True).model_dump_json(), kind=TASK_KIND, period_key=period,
    )
    db.add(task)
    db.flush()
    today = now.date()
    for group in groups:
        assignment = TaskAssignment(task_id=task.id, study_group_id=group.id, status="new", locked=False)
        db.add(assignment)
        db.flush()
        for curator in task_service.assignees(db, group.id, today):
            in_app_notification_service.notify(
                db, curator, "task_assigned",
                f"Новая задача «{task.title}» для группы {group.code}, срок — {deadline.strftime('%d.%m.%Y %H:%M')}.",
                entity_type="task_assignment", entity_id=str(assignment.id),
            )
    db.commit()
    return task


# ---------- кому что видно ----------

def visible_groups(db: Session, user: User, department_id: int | None = None) -> list[StudyGroup]:
    """Активные группы не на договорной основе, которые пользователь видит в своде питания."""
    # Отделение и назначения куратора — сразу, без запроса на каждую группу при сборке свода.
    query = db.query(StudyGroup).options(
        joinedload(StudyGroup.department),
        selectinload(StudyGroup.curator_assignments).joinedload(CuratorAssignment.user),
    ).filter(StudyGroup.is_active.is_(True))
    if RoleCode(user.role.code) in DEPARTMENT_SCOPED_ROLES:
        if user.department_id is None:
            return []
        query = query.filter(StudyGroup.department_id == user.department_id)
    elif department_id is not None:
        query = query.filter(StudyGroup.department_id == department_id)
    return [g for g in query.order_by(StudyGroup.course, StudyGroup.code).all()]


# ---------- выгрузка для ответственной по питанию ----------

def export_workbook(overview) -> bytes:
    """Книга Excel по образцу колледжа: лист на отделение; № п/п, группа, куратор, число питающихся и заказ по дням
    недели, итоги, статус подачи. Числа «по прогнозу» выделены цветом и курсивом."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    from app.core.xlsx import append_row

    status_ru = {"submitted": "подано куратором", "pending": "ещё не подано", "forecast": "по прогнозу"}
    forecast_fill = PatternFill("solid", fgColor="FFF2CC")
    wb = Workbook()
    wb.remove(wb.active)
    by_department: dict[str, list] = {}
    for row in overview.rows:
        by_department.setdefault(row.department_name, []).append(row)
    if not by_department:
        by_department = {"Питание": []}
    for name, rows in by_department.items():
        title = "".join(ch for ch in name if ch not in '[]:*?/\\')[:31] or "Питание"
        ws = wb.create_sheet(title)
        last = overview.week_start + datetime.timedelta(days=5)
        append_row(ws, [f"Питание на неделю {overview.week_start.strftime('%d.%m.%Y')}–{last.strftime('%d.%m.%Y')}"])
        ws["A1"].font = Font(bold=True, size=13)
        append_row(ws, ["№ п/п", "Группа", "Куратор", "Питающихся в группе"] + [d.strftime("%d.%m") for d in overview.dates] + ["Подача"])
        for cell in ws[2]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        totals = {d: 0 for d in overview.dates}
        for i, r in enumerate(rows, start=1):
            counts = {d.date: d for d in r.days}
            append_row(ws, [i, r.code, r.curator_name or "нет куратора", r.eaters]
                       + [counts[d].count if d in counts else "" for d in overview.dates] + [status_ru.get(r.status, r.status)])
            for offset, d in enumerate(overview.dates):
                value = counts.get(d)
                cell = ws.cell(row=ws.max_row, column=5 + offset)
                if value is not None:
                    totals[d] += value.count
                    if value.source == "forecast":
                        cell.fill, cell.font = forecast_fill, Font(italic=True)
                    elif value.source == "edited":
                        cell.font = Font(bold=True)
        append_row(ws, ["", "", "Итого", sum(r.eaters for r in rows)] + [totals[d] for d in overview.dates] + [""])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 28
        ws.column_dimensions["D"].width = 14
        ws.column_dimensions[chr(ord("E") + len(overview.dates))].width = 18
        ws.freeze_panes = "E3"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
