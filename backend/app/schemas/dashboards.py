import datetime

from pydantic import BaseModel


class DayOverviewRow(BaseModel):
    study_group_id: int
    code: str
    course: int
    in_list: int
    present: int
    late: int
    absent_excused: int
    absent_unexcused: int
    percent: float
    is_submitted: bool
    is_on_time: bool | None


class DynamicsPoint(BaseModel):
    date: datetime.date
    percent: float
    in_list: int
    present: int


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


