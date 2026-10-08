import datetime

from pydantic import BaseModel, Field


class MealStudentRead(BaseModel):
    student_id: int
    full_name: str
    eats: bool
    locked_reason: str | None = None  # почему питание включить нельзя (договорная основа)


class MealDayRead(BaseModel):
    date: datetime.date
    count: int
    source: str  # submitted / edited / forecast
    open: bool
    cutoff: datetime.datetime


class MealWeekRead(BaseModel):
    week_start: datetime.date
    status: str  # submitted / pending / forecast
    deadline: datetime.datetime
    submitted_count: int | None = None
    submitted_at: datetime.datetime | None = None
    forecast: int
    days: list[MealDayRead]


class GroupMealsRead(BaseModel):
    study_group_id: int
    code: str
    funding: str | None
    can_edit: bool
    eaters: int
    students: list[MealStudentRead]
    attendance_percent: float | None
    hint: int
    weeks: list[MealWeekRead]  # текущая и следующая недели


class MealSetStudent(BaseModel):
    eats: bool


class MealSubmitWeek(BaseModel):
    week_start: datetime.date
    count: int = Field(ge=0, le=1000)


class MealSetDay(BaseModel):
    date: datetime.date
    count: int | None = Field(default=None, ge=0, le=1000)  # None — вернуть недельное число


class MealOverviewDay(BaseModel):
    date: datetime.date
    count: int
    source: str


class MealOverviewRow(BaseModel):
    study_group_id: int
    code: str
    course: int
    department_id: int
    department_name: str
    curator_name: str | None
    eaters: int
    attendance_percent: float | None
    status: str
    submitted_at: datetime.datetime | None
    days: list[MealOverviewDay]


class MealOverview(BaseModel):
    week_start: datetime.date
    deadline: datetime.datetime
    dates: list[datetime.date]
    rows: list[MealOverviewRow]
    totals: dict[str, int]  # дата ISO → сумма по выбранным группам
