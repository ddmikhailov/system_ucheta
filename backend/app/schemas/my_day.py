import datetime
from typing import Literal

from pydantic import BaseModel


class RhythmDay(BaseModel):
    """День в «ритме группы»: off — занятий нет, missing — учебный день не сдан, absent — есть пропуски
    без уважительной причины (absent — сколько), ok — все на месте или отсутствуют по уважительной."""
    date: datetime.date
    kind: Literal["off", "missing", "absent", "ok"]
    absent: int = 0


class DayGroup(BaseModel):
    id: int
    code: str
    course: int
    # submitted — день сдан; pending — учебный день, ещё не сдан; no_study_day — сегодня занятий нет
    today_status: Literal["submitted", "pending", "no_study_day"]
    is_on_time: bool | None = None
    # Несданные учебные дни за последние дни (самые свежие первыми); missed_total — сколько их всего в окне
    missed_dates: list[datetime.date]
    missed_total: int
    # Последние три недели по дням (от старых к новым) — полоса «ритм группы» в «Моём дне».
    rhythm: list[RhythmDay] = []


class DayTask(BaseModel):
    assignment_id: int
    title: str
    group_code: str
    due_date: datetime.date
    kind: Literal["overdue", "returned", "due_soon"]
    status: str
    days_left: int  # отрицательное — просрочено на столько дней


class AttentionStudent(BaseModel):
    student_id: int
    full_name: str
    group_code: str
    risk_streak: int
    attendance_percent: float | None  # посещаемость с начала семестра, %
    needs_work: bool  # студент в группе риска, а записей об индивидуальной работе давно нет
    last_work_on: datetime.date | None
    follow_up_on: datetime.date | None
    follow_up_overdue: bool
    follow_up_today: bool


class Birthday(BaseModel):
    student_id: int
    full_name: str
    group_code: str
    date: datetime.date  # ближайший день рождения
    days_until: int
    turns: int


class ReviewWaiting(BaseModel):
    count: int
    oldest_submitted_at: datetime.datetime | None


class MyDay(BaseModel):
    today: datetime.date
    leads_groups: bool
    groups: list[DayGroup]
    tasks: list[DayTask]
    attention: list[AttentionStudent]
    attention_total: int
    no_work_days: int  # через сколько дней без записей серия пропусков считается «нужна работа»
    birthdays: list[Birthday]
    review_waiting: ReviewWaiting | None


class AbsenceLine(BaseModel):
    date: datetime.date
    code: str
    name: str


class AbsenceMessage(BaseModel):
    days: int
    absences: list[AbsenceLine]
    text: str
