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
    streak: int


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


