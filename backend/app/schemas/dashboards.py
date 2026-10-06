import datetime

from pydantic import BaseModel


class DayOverviewRow(BaseModel):
    study_group_id: int
    code: str
    course: int
    responsible_name: str | None = None
    # None, если день ещё не сдан — раньше несданный день молча считался за
    # 100% присутствия (см. TODO.md 3), теперь фронт показывает «—».
    in_list: int | None
    present: int | None
    late: int | None
    absent_excused: int | None
    absent_unexcused: int | None
    percent: float | None
    is_submitted: bool
    is_on_time: bool | None


class DynamicsPoint(BaseModel):
    date: datetime.date
    percent: float | None
    in_list: int | None
    present: int | None


class RiskStudentRow(BaseModel):
    student_id: int
    full_name: str
    study_group_id: int
    group_code: str
    streak: int  # дней подряд «н» — справочно
    attendance_percent: float  # посещаемость с начала семестра, %
    days: int  # сданных дней
    absent: int  # пропущено из них


class CuratorDisciplineRow(BaseModel):
    study_group_id: int
    code: str
    course: int
    responsible_name: str | None = None
    on_time: int
    late: int
    missed: int
    total_study_days: int


class StudentMarkHistoryEntry(BaseModel):
    date: datetime.date
    mark_code: str
    mark_name: str
    basis_reference: str | None
    basis_status: str


class StudentCard(BaseModel):
    student_id: int
    full_name: str
    group_code: str
    status: str
    percent_period: float
    history: list[StudentMarkHistoryEntry]


class SummaryCode(BaseModel):
    code: str
    name: str
    # Код считается присутствием (например, «опоздание») — фронт по нему
    # отличает пропуски при выборе столбцов.
    counts_as_present: bool


class SummaryLineRead(BaseModel):
    """Строка свода: отделение (или «Все отделения») × срез («Всего» /
    «К 1 паре»), за день (`date`) или за весь период (`date is None`)."""

    date: datetime.date | None
    department: str
    slice_name: str
    groups: int
    groups_submitted: int
    headcount: int
    counted: int
    present: int
    absent: int
    percent: float | None
    by_code: dict[str, int]


class SummaryGroupDayRead(BaseModel):
    date: datetime.date
    department: str
    group_id: int
    group_code: str
    course: int
    headcount: int
    is_submitted: bool
    present: int | None
    absent: int | None
    percent: float | None
    first_period: int | None
    by_code: dict[str, int]


class SummaryRead(BaseModel):
    codes: list[SummaryCode]
    daily: list[SummaryLineRead]
    period: list[SummaryLineRead]
    group_days: list[SummaryGroupDayRead]


class CuratorDayRow(BaseModel):
    date: datetime.date
    # on_time — сдано в день занятия; late — задним числом; missed — не сдано.
    status: str
    # Местное время колледжа (уже переведено с UTC на сервере), время
    # ПОСЛЕДНЕЙ сдачи дня; None, если день не сдан.
    submitted_at_local: datetime.datetime | None
    submitted_by: str | None
    first_period: int | None
    days_late: int | None


class CuratorDaysRead(BaseModel):
    study_group_id: int
    group_code: str
    responsible_name: str | None
    date_from: datetime.date
    date_to: datetime.date
    on_time: int
    late: int
    missed: int
    total_study_days: int
    # Среднее время сдачи по дням «вовремя», ЧЧ:ММ; None, если таких нет.
    average_on_time_submission: str | None
    days: list[CuratorDayRow]
